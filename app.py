import base64
import json
import os
import requests
import urllib

from apiclient.discovery import build
from messenger import Bot
from flask import Flask, Response, render_template, request
from wiki_scraper import get_nutrition_facts_from_wiki, get_wikipedia_url

app = Flask(__name__)

VALIDATION_TOKEN = os.environ.get('FB_VALDIATION_TOKEN') or 'test'
MESSENGER_PAGE_ACCESS_TOKEN = os.environ.get('MESSENGER_PAGE_ACCESS_TOKEN')
GOOGLE_VISION_API_KEY = os.environ.get('GOOGLE_VISION_API_KEY')

gvision = build('vision', 'v1', developerKey=GOOGLE_VISION_API_KEY)


class Nutri(Bot):

    def handle_message(self, messaging_event):
        print messaging_event, messaging_event.get('message')
        message = messaging_event.get('message')
        attachments = message.get('attachments', [])

        if attachments and 'image' == attachments[0]['type']:
            sender_id = messaging_event['sender']['id']
            respond(sender_id, 'Checking what this is...')
            set_typing(sender_id)
            buttons = None

            descriptions = get_google_image_descriptions(attachments)
            text = 'I think you cannot eat that. Maybe show it to me from a different angle.'
            if 'food' in descriptions:
                guessed_food_name, nutrition_facts = get_nutrition_facts(descriptions)
                text = build_response_text(guessed_food_name, nutrition_facts)
                buttons = build_response_buttons(buttons, guessed_food_name, text)

            respond(sender_id, text, buttons=buttons)


nutri = Nutri(VALIDATION_TOKEN, MESSENGER_PAGE_ACCESS_TOKEN)


@app.route('/healthcheck')
def healthcheck():
    return Response('OK', 200)


@app.route('/about')
def about():
    return render_template('about.html')


@app.route('/webhook', methods=['POST', 'GET'])
def webhook():
    if request.method == 'GET':
        return handle_get(request)
    elif request.method == 'POST':
        return handle_post(request)


def handle_get(request):
    mode = request.args.get('hub.mode')
    verify_token = request.args.get('hub.verify_token')

    response = Response(request.args.get('hub.challenge'), 200)
    if verify_token != VALIDATION_TOKEN:
        response = Response('', 403)

    return response


def handle_post(request):
    data = request.json
    nutri.process_message(data)
    return Response('', 200)


def build_response_buttons(buttons, guessed_food_name, text):
    if text and guessed_food_name:
        buttons = [{
            'type': 'web_url',
            'url': get_wikipedia_url(guessed_food_name),
            'title': 'More info'
        }]
    return buttons


def build_response_text(guessed_food_name, nutrition_facts):
    text = '\n'.join(' '.join(nutrition_fact) for nutrition_fact in nutrition_facts).encode('utf-8')
    if text and guessed_food_name:
        text = 'This looks like {article} {guessed_food_name} to me. Here are the facts I could gather:\n'.format(
            article='an' if guessed_food_name[0].lower() in 'aeiou' else 'a',
            guessed_food_name=guessed_food_name
        ) + text
    else:
        text = 'Even though it looks like food. I couldn\'t find anything useful on it.'
    return text


def get_nutrition_facts(descriptions):
    nutrition_facts = []
    for description in descriptions:
        nutrition_fact = get_nutrition_facts_from_wiki(description)
        if nutrition_fact:
            nutrition_facts += nutrition_fact
            return description, nutrition_facts
    return '', []


def get_google_image_descriptions(attachments):
    opener = urllib.urlopen(attachments[0]['payload']['url'])
    image_content = base64.b64encode(opener.read())
    gvision_request = gvision.images().annotate(body={
        'requests': [{
            'image': {
                'content': image_content
            },
            'features': [{
                'type': 'LABEL_DETECTION',
                'maxResults': 8
            }]
        }]
    })
    api_response = gvision_request.execute()
    descriptions = []
    if api_response.get('responses'):
        descriptions = [annotation['description'] for annotation in api_response['responses'][0]['labelAnnotations']]
        print 'google_vision_api_responses {descriptions}'.format(
            descriptions=descriptions
        )
    return descriptions


def respond(recipient_id, text, buttons=None):
    payload = {
        'recipient': {
            'id': recipient_id,
        }
    }
    if buttons:
        payload.update({
            'message': {
                'attachment': {
                    'type': 'template',
                    'payload': {
                        'template_type': 'button',
                        'text': text,
                        'buttons': buttons
                    }
                }
            }
        })
    else:
        payload.update({
            'message': {
                'text': text,
            }
        })

    requests.post('https://graph.facebook.com/v2.6/me/messages?access_token={access_token}'.format(
        access_token=MESSENGER_PAGE_ACCESS_TOKEN
    ), data=json.dumps(payload), headers={
        'content-type': 'application/json'
    })


def set_typing(recipient_id):
    requests.post('https://graph.facebook.com/v2.6/me/messages?access_token={access_token}'.format(
        access_token=MESSENGER_PAGE_ACCESS_TOKEN
    ), data=json.dumps({
        'recipient': {
            'id': recipient_id
        },
        'sender_action': 'typing_on'
    }), headers={
        'content-type': 'application/json'
    })
