import sqlite3
from fetch_events import fetch_economic_events

def save_to_db(events):
    conn = sqlite3.connect('C:\Users\Khaled\Documents\GitHub\finance\economic_calander\data\economic_events.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS events
                 (id INTEGER PRIMARY KEY, date TEXT, time TEXT, event TEXT, country TEXT, currency TEXT,
                  previous REAL, estimate REAL, actual REAL, change REAL, impact TEXT, changePercentage REAL, unit TEXT)''')
    
    for event in events:
        event_date, event_time = event['date'].split()
        event_data = (
            event_date, event_time, event['event'], event['country'], event['currency'],
            event['previous'], event['estimate'], event['actual'], event['change'],
            event['impact'], event['changePercentage'], event['unit']
        )
        
        c.execute('''INSERT INTO events (date, time, event, country, currency, previous, estimate, actual, change, impact, changePercentage, unit)
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''', event_data)
    
    conn.commit()
    conn.close()

if __name__ == "__main__":
    events = fetch_economic_events()
    save_to_db(events)
