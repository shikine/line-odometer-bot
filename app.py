from flask import Flask, request
import os
import json
import requests
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

app = Flask(__name__)
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_REPLY_ENDPOINT = 'https://api.line.me/v2/bot/message/reply'

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def get_user_data(user_id):
    res = supabase.table("car_data").select("*").eq("user_id", user_id).execute()
    if res.data:
        cars = {c["car"]: {
            "start_km": c["start_km"],
            "max_km": c["max_km"],
            "last_km": c["last_km"]
        } for c in res.data}
    else:
        cars = {
            "ジムニー": {"max_km": 0, "start_km": 0, "last_km": 0},
            "ラパン": {"max_km": 0, "start_km": 0, "last_km": 0}
        }
    return {
        "selected_car": "ジムニー",
        "cars": cars,
        "state": None
    }

def save_user_car(user_id, car, car_data):
    supabase.table("car_data").upsert({
        "user_id": user_id,
        "car": car,
        "start_km": car_data["start_km"],
        "max_km": car_data["max_km"],
        "last_km": car_data["last_km"]
    }).execute()

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

            if 'user_data' not in locals():
                user_data = {}
            if user_id not in user_data:
                user_data[user_id] = get_user_data(user_id)

            user = user_data[user_id]
            selected_car = user["selected_car"]
            car_data = user["cars"][selected_car]

            if text.lower() in ["スタート", "メニュー"]:
                buttons = [
                    {"type": "postback", "label": "ジムニーの管理", "data": "action=select_car&car=ジムニー"},
                    {"type": "postback", "label": "ラパンの管理", "data": "action=select_car&car=ラパン"},
                    {"type": "message", "label": "リセット", "text": "リセット"}
                ]
                send_reply(reply_token, "以下のオプションから選択してください。", buttons)

            elif text in ["ジムニー", "ラパン"]:
                user["selected_car"] = text
                car_data = user["cars"][text]

                if car_data["start_km"] == 0:
                    send_reply(reply_token, f"{text} を選択しました。開始メーターの走行距離を入力してください（例：30000）。")
                    user["state"] = "awaiting_start_km_for_both"
                elif car_data["max_km"] == 0:
                    send_reply(reply_token, f"{text} を選択しました。保険の上限距離を入力してください（例：5000）。")
                    user["state"] = "awaiting_max_km"
                else:
                    run_km = car_data["last_km"] - car_data["start_km"]
                    upper_limit_km = car_data["start_km"] + car_data["max_km"]
                    remaining = car_data["max_km"] - run_km
                    msg = (
                        f"{text} を選択しました。\n"
                        f"開始メーター: {car_data['start_km']}km\n"
                        f"保険の上限距離: {car_data['max_km']}km\n"
                        f"保険対象終了メーター: {upper_limit_km}km\n"
                        f"現在の距離: {car_data['last_km']}km\n"
                        f"上限まで残り: {remaining}km"
                    )
                    send_reply(reply_token, msg)

            elif text.isdigit():
                current_km = int(text)
                state = user["state"]
                if state == "awaiting_start_km_for_both":
                    car_data["start_km"] = current_km
                    car_data["last_km"] = current_km
                    user["state"] = "awaiting_max_km_after_start"
                    send_reply(reply_token, f"開始メーターを {current_km}km に設定しました。次に保険の上限距離を教えてください。")
                elif state in ["awaiting_max_km", "awaiting_max_km_after_start", "updating_max_km"]:
                    car_data["max_km"] = current_km
                    user["state"] = None
                    run_km = car_data["last_km"] - car_data["start_km"]
                    upper_limit_km = car_data["start_km"] + car_data["max_km"]
                    remaining = car_data["max_km"] - run_km
                    msg = (
                        f"{selected_car} の保険上限距離を {current_km}km に設定しました。\n"
                        f"開始メーター: {car_data['start_km']}km\n"
                        f"保険対象終了メーター: {upper_limit_km}km\n"
                        f"現在の距離: {car_data['last_km']}km\n"
                        f"上限まで残り: {remaining}km"
                    )
                    send_reply(reply_token, msg)
                else:
                    car_data["last_km"] = current_km
                    run_km = current_km - car_data["start_km"]
                    remaining = car_data["max_km"] - run_km
                    msg = f"{selected_car} - 現在の走行距離: {run_km}km\n残り: {remaining}km"
                    send_reply(reply_token, msg)

                save_user_car(user_id, selected_car, car_data)

            elif text == "リセット":
                user["cars"][selected_car] = {"max_km": 0, "start_km": 0, "last_km": 0}
                user["state"] = None
                save_user_car(user_id, selected_car, user["cars"][selected_car])
                send_reply(reply_token, f"{selected_car} のデータをリセットしました。")

            else:
                send_reply(reply_token, "メーター数値を送るか、『ジムニー』『ラパン』『距離上限設定』『現在の走行距離』『保険の上限距離を更新』などを送信してください。")

    return "OK"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)
