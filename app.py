from flask import Flask, request
import os
import json
import requests
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_REPLY_ENDPOINT = 'https://api.line.me/v2/bot/message/reply'

user_data = {}


def send_reply(reply_token, text, buttons=None):
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}"
    }

    if buttons:
        payload = {
            "replyToken": reply_token,
            "messages": [{
                "type": "template",
                "altText": "メニュー",
                "template": {
                    "type": "buttons",
                    "text": text,
                    "actions": buttons
                }
            }]
        }
    else:
        payload = {
            "replyToken": reply_token,
            "messages": [{"type": "text", "text": text}]
        }

    requests.post(LINE_REPLY_ENDPOINT, headers=headers, data=json.dumps(payload))


@app.route("/callback", methods=['POST'])
def callback():
    body = request.get_json()
    for event in body['events']:
        if event['type'] != 'message':
            continue

        msg = event['message']
        reply_token = event['replyToken']
        user_id = event['source']['userId']

        if msg['type'] == 'text':
            text = msg['text'].strip()

            if user_id not in user_data:
                user_data[user_id] = {
                    "selected_car": "ジムニー",
                    "cars": {
                        "ジムニー": {"max_km": 0, "start_km": 0, "last_km": 0},
                        "ラパン": {"max_km": 0, "start_km": 0, "last_km": 0}
                    },
                    "state": None
                }

            user = user_data[user_id]
            selected_car = user["selected_car"]

            if text.lower() in ["スタート", "メニュー"]:
                buttons = [
                    {
                        "type": "postback",
                        "label": "ジムニーの管理",
                        "data": "action=select_car&car=ジムニー"
                    },
                    {
                        "type": "postback",
                        "label": "ラパンの管理",
                        "data": "action=select_car&car=ラパン"
                    },
                    {
                        "type": "message",
                        "label": "リセット",
                        "text": "リセット"
                    }
                ]
                send_reply(reply_token, "以下のオプションから選択してください。", buttons)

            elif text in ["ジムニー", "ラパン"]:
                user["selected_car"] = text
                car_data = user["cars"][text]
                start_km = car_data.get("start_km", 0)
                max_km = car_data.get("max_km", 0)
                last_km = car_data.get("last_km", 0)
                if start_km and max_km:
                    run_km = last_km - start_km
                    upper_limit_km = start_km + max_km
                    remaining = max_km - run_km
                    msg = (
    f"{text} を選択しました。
"
    f"開始メーター: {start_km}km
"
    f"保険の上限距離: {max_km}km
"
    f"保険対象終了メーター: {upper_limit_km}km
"
    f"現在の距離: {last_km}km
"
    f"上限まで残り: {remaining}km"
)
)
if remaining < 0:
    msg += "
🚨 保険の上限距離を超えています。"
elif remaining < 300:
    msg += "
⚠️ 保険の上限に近づいています。"
                    if remaining < 0:
                        msg += "
🚨 保険の上限距離を超えています。"
                    elif remaining < 300:
                        msg += "
⚠️ 保険の上限に近づいています。"
                    send_reply(reply_token, msg)
                else:
                    send_reply(reply_token, f"{text} を選択しました。走行距離管理を開始できます。")

            elif text == "距離上限設定":
                send_reply(reply_token, "開始メーターの走行距離を教えてください。")
                user["state"] = "awaiting_start_km_for_limit"

            elif text == "保険の上限距離を更新":
                send_reply(reply_token, "新しい保険の上限距離を教えてください。")
                user["state"] = "updating_max_km"

            elif text == "現在の走行距離":
                send_reply(reply_token, "現在の走行距離を教えてください。")
                user["state"] = "awaiting_current_km"

            elif text.isdigit():
                current_km = int(text)
                car = selected_car

                if user.get("state") == "awaiting_start_km_for_limit":
                    user["cars"][car]["start_km"] = current_km
                    send_reply(reply_token, f"{car} の開始メーターを {current_km}km に設定しました。次に保険の上限距離を教えてください。")
                    user["state"] = "awaiting_max_km"
                    continue

                if user.get("state") == "awaiting_max_km":
                    user["cars"][car]["max_km"] = current_km
                    user["state"] = None
                    send_reply(reply_token, f"{car} の保険上限距離を {current_km}km に設定しました。")
                    continue

                if user.get("state") == "updating_max_km":
                    user["cars"][car]["max_km"] = current_km
                    user["state"] = None
                    send_reply(reply_token, f"{car} の保険上限距離を {current_km}km に更新しました。")
                    continue

                if user.get("state") == "awaiting_current_km":
                    car_data = user["cars"][car]
                    if car_data["start_km"] == 0:
                        car_data["start_km"] = current_km
                        send_reply(reply_token, f"{car} の開始メーターを {current_km}km に設定しました。")
                        if car_data["max_km"] == 0:
                            send_reply(reply_token, f"{car} の保険上限距離が未設定です。『距離上限設定』と入力して設定してください。")
                    else:
                        run_km = current_km - car_data["start_km"]
                        remaining = car_data["max_km"] - run_km
                        car_data["last_km"] = current_km
                        msg = f"{car} - 現在の走行距離: {run_km}km\n残り: {remaining}km"
                        if remaining < 300:
                            msg += "\n⚠️ 保険の上限に近づいています！"
                        send_reply(reply_token, msg)
                    user["state"] = None
                    continue

                car_data = user["cars"][car]
                if car_data["start_km"] == 0:
                    car_data["start_km"] = current_km
                    car_data["last_km"] = current_km
                    send_reply(reply_token, f"{car} の開始メーターを {current_km}km に設定しました。")
                    if car_data["max_km"] == 0:
                        send_reply(reply_token, f"{car} の保険上限距離が未設定です。『距離上限設定』と入力して設定してください。")
                else:
                    run_km = current_km - car_data["start_km"]
                    remaining = car_data["max_km"] - run_km
                    car_data["last_km"] = current_km

                    msg = f"{car} - 現在の走行距離: {run_km}km\n残り: {remaining}km"
                    if remaining < 300:
                        msg += "\n⚠️ 保険の上限に近づいています！"
                    send_reply(reply_token, msg)

            elif text == "リセット":
                selected_car = user["selected_car"]
                user["cars"][selected_car] = {"max_km": 0, "start_km": 0, "last_km": 0}
                send_reply(reply_token, f"{selected_car} のデータをリセットしました。再設定をお願いします。")

            else:
                send_reply(reply_token, "メーター数値を送るか、『ジムニー』『ラパン』『距離上限設定』『現在の走行距離』『保険の上限距離を更新』などを送信してください。")

    return "OK"


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)
