import vk_api
from vk_api.bot_longpoll import VkBotLongPoll, VkBotEventType
from vk_api.utils import get_random_id
from vk_api import VkUpload
import argparse
import threading
import queue
import requests
import time

import config
import const
from const import Msg as msgid
import facecomparator
import bot_logger
import user

vk_session = vk_api.VkApi(token=config.vk_token, api_version='5.103')
longpoll = VkBotLongPoll(vk_session, group_id=config.group_id)
vk = vk_session.get_api()
upload = VkUpload(vk_session)


def create_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument("-s", "--silent", action="store_true", default=False)
    parser.add_argument("-l", "--no-save-log", action="store_true", default=False)
    parser.add_argument("-p", "--use-proxy", action="store_true", default=False)
    return parser


def do_work_thread():
    users = {}
    while True:
        item = q.get()
        if item is None:
            break
        file_url = item[0]
        user_id = item[1]

        cur_user = users.setdefault(user_id, user.User(user_id, fc, user_name=str(user_id)))
        downloaded_file = requests.get(url=file_url).content
        result = cur_user.photo_process(downloaded_file)

        vk.messages.send(user_id=user_id, random_id=get_random_id(),
                         message=msg_dict[msgid.msg_photo_received.value].format(cur_user.get_cnt()))

        log.log("<{}> File has been received.".format(user_id))

        if result > 1:
            vk.messages.send(user_id=user_id, random_id=get_random_id(),
                             message=msg_dict[msgid.msg_both_photos_received.value])
            log.log("<{}> Both file received. Start to proceed.".format(user_id))
            result = cur_user.compare()

            distance = result['distance']
            if distance:
                file1, file2 = result['file1'] + '.jpg', result['file2'] + '.jpg'
                attach = upload.photo_messages([file1, file2])
                faces = ["photo" + str(a['owner_id']) + "_" + str(a['id']) for a in attach]
                decision = make_decision(distance)
                m = decision + " (" + str(distance) + ")"
                vk.messages.send(user_id=user_id, random_id=get_random_id(), message=m, attachment=faces)
                log.log("<{}> Distance: {}.".format(user_id, distance))
                log.log("<{}> Decision: {}.".format(user_id, decision))
            else:
                vk.messages.send(user_id=user_id, random_id=get_random_id(),
                                 message=msg_dict[msgid.msg_face_detection_error.value].format(result['error']))
                log.log("<{}>".format(user_id) + msg_dict[msgid.msg_face_detection_error.value].format(result['error']))
        q.task_done()


def make_decision(dist):
    if dist == 0.0:
        return msg_dict[msgid.msg_decision_same_photos.value]
    if dist <= 0.55:
        return msg_dict[msgid.msg_decision_yes.value]
    if dist <= 0.6:
        return msg_dict[msgid.msg_decision_maybe.value]
    return msg_dict[msgid.msg_decision_no.value]


if __name__ == "__main__":
    args = create_parser().parse_args()
    log = bot_logger.BotLogger(silent=args.silent, nosavelog=args.no_save_log, startparams=vars(args))
    print("Args: ", args)

    fc = facecomparator.FaceCompare()
    msg_dict = const.russian

    q = queue.Queue()
    t1 = threading.Thread(target=do_work_thread)
    t1.start()

    while True:
        try:
            for event in longpoll.listen():
                if event.type == VkBotEventType.MESSAGE_NEW:
                    # print(event.obj)
                    user_id = event.obj.message['from_id']
                    if len(event.obj.message['fwd_messages']):
                        attachments = event.obj.message['fwd_messages'][0]['attachments']
                    else:
                        attachments = event.obj.message['attachments']
                    if 0 < len(attachments) < 3:
                        for a in attachments:
                            if a['type'] == 'photo':
                                sizes = a['photo']['sizes']
                                for s in sizes:
                                    if s['type'] == 'x':
                                        pic = s['url']
                                        break
                                item = [pic, user_id]
                                q.put(item)
                    elif event.obj.message['text'] == '/log':
                        logfile = upload.document(log.get_file_path(), title=log.get_file_path(),
                                                  message_peer_id=user_id)['doc']
                        doc = "doc" + str(logfile['owner_id']) + "_" + str(logfile['id'])
                        vk.messages.send(user_id=user_id, random_id=get_random_id(), attachment=doc)
                    else:
                        vk.messages.send(user_id=user_id, random_id=get_random_id(),
                                         message=msg_dict[msgid.msg_need_2_photos.value])
        except Exception as e:
            log.log("Error: " + str(e))
            time.sleep(10)
