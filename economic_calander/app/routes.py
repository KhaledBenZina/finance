from flask import Blueprint, jsonify, render_template
from app.database import get_events

main = Blueprint('main', __name__)

@main.route('/api/events')
def api_events():
    events = get_events()
    events_list = [
        {
            'title': event['event'],
            'start': f"{event['date']}T{event['time']}",
            'description': event['description'],
            'impact': event['impact']
        } for event in events
    ]
    return jsonify(events_list)

@main.route('/')
def index():
    return render_template('index.html')
