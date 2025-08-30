#!/usr/bin/env python3
"""
Enhanced Hotel Monitor with State Tracking and Multiple Notifications
Designed for GitHub Actions but works anywhere
"""

import requests
import json
import re
import os
import time
from datetime import datetime, timedelta
from dataclasses import dataclass
from typing import List, Dict, Optional
import logging

@dataclass
class RoomAvailability:
    room_name: str
    date: str
    available_count: int
    price: str
    status: str  # 'available', 'sold_out', 'not_bookable'

class EnhancedHotelMonitor:
    def __init__(self):
        self.config = {
            'hotel_id': '20000122',
            'plan_id': '2',
            'target_dates': ['2025-10-24', '2025-10-25'],
            'api_url': 'https://www2.489pro.com/www1/api/ypro/v2plus/ypro_stocksearch_api.asp',
            'check_interval': 300,  # 5 minutes
            'state_file': 'monitor_state.json',
            'log_file': 'hotel_monitor.log'
        }
        
        # Notification settings from environment
        self.notifications = {
            'email': {
                'enabled': bool(os.getenv('EMAIL_USER')),
                'smtp_server': os.getenv('SMTP_SERVER', 'smtp.gmail.com'),
                'smtp_port': int(os.getenv('SMTP_PORT', '587')) if os.getenv('SMTP_PORT') else 587,
                'user': os.getenv('EMAIL_USER'),
                'password': os.getenv('EMAIL_PASS'),
                'to': os.getenv('NOTIFY_EMAIL')
            },
            'discord': {
                'enabled': bool(os.getenv('DISCORD_WEBHOOK')),
                'webhook': os.getenv('DISCORD_WEBHOOK')
            },
            'slack': {
                'enabled': bool(os.getenv('SLACK_WEBHOOK')),
                'webhook': os.getenv('SLACK_WEBHOOK')
            },
            'pushover': {
                'enabled': bool(os.getenv('PUSHOVER_TOKEN')),
                'token': os.getenv('PUSHOVER_TOKEN'),
                'user': os.getenv('PUSHOVER_USER')
            },
            'telegram': {
                'enabled': bool(os.getenv('TELEGRAM_BOT_TOKEN') and os.getenv('TELEGRAM_CHAT_ID')),
                'bot_token': os.getenv('TELEGRAM_BOT_TOKEN'),
                'chat_id': os.getenv('TELEGRAM_CHAT_ID')
            }
        }
        
        self.setup_logging()
        self.session = self.setup_session()
    
    def setup_logging(self):
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(self.config['log_file']),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
    
    def setup_session(self):
        session = requests.Session()
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': '*/*',
            'Accept-Language': 'en-US,en;q=0.9,ja;q=0.8',
            'Referer': 'https://www.489pro.com/'
        })
        return session
    
    def get_week_dates(self, target_date: str) -> tuple:
        """Get week range for API call"""
        from datetime import datetime, timedelta
        target_dt = datetime.strptime(target_date, "%Y-%m-%d")
        days_from_monday = target_dt.weekday()
        monday = target_dt - timedelta(days=days_from_monday)
        start_date = monday.strftime("%Y/%m/%d")
        end_date = (monday + timedelta(days=6)).strftime("%Y/%m/%d")
        return start_date, end_date
    
    def call_api(self) -> Optional[dict]:
        """Call hotel API and return parsed data"""
        try:
            # Get date range for first target date
            start_date, end_date = self.get_week_dates(self.config['target_dates'][0])
            
            timestamp = str(int(time.time() * 1000))
            params = {
                'id': self.config['hotel_id'],
                'planId': self.config['plan_id'],
                'startDate': start_date,
                'endDate': end_date,
                'input_data': f'id=stock_calendar_1,start_date={start_date},end_date={end_date},select_room=,select_plan={self.config["plan_id"]},user_num=2,init_flag=0,disp_cal_room=1,disp_cal_plan=,disp_cal_plan_btn=1,init_plan_num=0,kid=',
                'ty': 'ser',
                'mo': '0',
                'meo': '0',
                'yr': 'YES',
                'lan': 'JPN',
                'pt': '-1',
                'mel': '-1',
                'pay': '0',
                'callback': f'jsonp{timestamp}',
                '_': timestamp
            }
            
            response = self.session.get(self.config['api_url'], params=params, timeout=30)
            response.raise_for_status()
            
            # Parse JSONP - the API uses getStockData instead of jsonp callback
            self.logger.debug(f"API response: {response.text[:200]}...")
            
            # Try different JSONP patterns
            json_match = re.search(r'(?:jsonp\d+|getStockData)\((.*)\);?\s*$', response.text, re.DOTALL)
            if not json_match:
                self.logger.error(f"Failed to parse JSONP response. First 500 chars: {response.text[:500]}")
                return None
            
            json_str = json_match[1]
            self.logger.debug(f"Extracted JSON: {json_str[:300]}...")
            
            # Fix JSON format - convert single quotes to double quotes and clean up
            json_str = json_str.replace("'", '"')
            
            # Handle HTML entities and control characters
            import html
            json_str = html.unescape(json_str)
            
            # Remove or replace problematic characters
            json_str = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', json_str)
            
            return json.loads(json_str)
            
        except Exception as e:
            self.logger.error(f"API call failed: {e}")
            return None
    
    def analyze_data(self, api_data: dict) -> List[RoomAvailability]:
        """Analyze API data and return availability info"""
        if not api_data or 'rooms' not in api_data:
            return []
        
        results = []
        
        for room in api_data.get('rooms', []):
            room_name = room.get('room_name_eng', f"Room {room.get('room_id')}")
            
            for aki in room.get('aki', []):
                date = aki.get('aki_date', '').replace('/', '-')
                
                if date in self.config['target_dates']:
                    available = int(aki.get('aki_num', 0))
                    sold_out = int(aki.get('sold_out_f', 0))
                    
                    # Get pricing
                    price = 'No price'
                    for plan in room.get('plans', []):
                        for price_info in plan.get('prices', []):
                            if price_info.get('price_date', '').replace('/', '-') == date:
                                if price_info.get('price_2', '0') != '0':
                                    price = f"¥{price_info.get('price_2')}"
                    
                    # Determine status
                    if available > 0:
                        status = 'available'
                    elif price != 'No price':
                        status = 'sold_out'
                    else:
                        status = 'not_bookable'
                    
                    results.append(RoomAvailability(
                        room_name=room_name,
                        date=date,
                        available_count=available,
                        price=price,
                        status=status
                    ))
        
        return results
    
    def load_state(self) -> dict:
        """Load previous state from file"""
        try:
            if os.path.exists(self.config['state_file']):
                with open(self.config['state_file'], 'r') as f:
                    return json.load(f)
        except Exception as e:
            self.logger.warning(f"Could not load state: {e}")
        return {'last_available': [], 'last_check': None}
    
    def save_state(self, state: dict):
        """Save current state to file"""
        try:
            with open(self.config['state_file'], 'w') as f:
                json.dump(state, f, indent=2, default=str)
        except Exception as e:
            self.logger.error(f"Could not save state: {e}")
    
    def detect_changes(self, current: List[RoomAvailability], previous: List[dict]) -> dict:
        """Detect changes in availability"""
        current_available = [
            {'room': r.room_name, 'date': r.date, 'count': r.available_count, 'price': r.price}
            for r in current if r.status == 'available'
        ]
        
        prev_available = previous
        
        # New rooms became available
        new_available = []
        for room in current_available:
            if not any(
                p['room'] == room['room'] and p['date'] == room['date'] 
                for p in prev_available
            ):
                new_available.append(room)
        
        # Rooms became unavailable
        lost_available = []
        for room in prev_available:
            if not any(
                c['room'] == room['room'] and c['date'] == room['date']
                for c in current_available
            ):
                lost_available.append(room)
        
        return {
            'new_available': new_available,
            'lost_available': lost_available,
            'current_available': current_available,
            'has_changes': bool(new_available or lost_available)
        }
    
    def send_email_notification(self, message: str, subject: str):
        """Send email notification"""
        if not self.notifications['email']['enabled']:
            return
        
        try:
            import smtplib
            from email.mime.text import MIMEText
            from email.mime.multipart import MIMEMultipart
            
            msg = MIMEMultipart()
            msg['From'] = self.notifications['email']['user']
            msg['To'] = self.notifications['email']['to']
            msg['Subject'] = subject
            
            msg.attach(MIMEText(message, 'plain'))
            
            server = smtplib.SMTP(
                self.notifications['email']['smtp_server'],
                self.notifications['email']['smtp_port']
            )
            server.starttls()
            server.login(
                self.notifications['email']['user'],
                self.notifications['email']['password']
            )
            server.sendmail(
                self.notifications['email']['user'],
                self.notifications['email']['to'],
                msg.as_string()
            )
            server.quit()
            
            self.logger.info("Email notification sent")
        except Exception as e:
            self.logger.error(f"Failed to send email: {e}")
    
    def send_discord_notification(self, message: str):
        """Send Discord webhook notification"""
        if not self.notifications['discord']['enabled']:
            return
        
        try:
            payload = {
                "content": message,
                "embeds": [{
                    "title": "Hotel Room Alert",
                    "description": message,
                    "color": 0x00ff00,
                    "timestamp": datetime.now().isoformat()
                }]
            }
            
            response = requests.post(
                self.notifications['discord']['webhook'],
                json=payload,
                timeout=10
            )
            response.raise_for_status()
            self.logger.info("Discord notification sent")
        except Exception as e:
            self.logger.error(f"Failed to send Discord notification: {e}")
    
    def send_slack_notification(self, message: str):
        """Send Slack webhook notification"""
        if not self.notifications['slack']['enabled']:
            return
        
        try:
            payload = {
                "text": "Hotel Room Alert",
                "blocks": [{
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": message
                    }
                }]
            }
            
            response = requests.post(
                self.notifications['slack']['webhook'],
                json=payload,
                timeout=10
            )
            response.raise_for_status()
            self.logger.info("Slack notification sent")
        except Exception as e:
            self.logger.error(f"Failed to send Slack notification: {e}")
    
    def send_pushover_notification(self, message: str, title: str):
        """Send Pushover notification"""
        if not self.notifications['pushover']['enabled']:
            return
        
        try:
            payload = {
                "token": self.notifications['pushover']['token'],
                "user": self.notifications['pushover']['user'],
                "message": message,
                "title": title,
                "priority": 1
            }
            
            response = requests.post(
                "https://api.pushover.net/1/messages.json",
                data=payload,
                timeout=10
            )
            response.raise_for_status()
            self.logger.info("Pushover notification sent")
        except Exception as e:
            self.logger.error(f"Failed to send Pushover notification: {e}")
    
    def send_telegram_notification(self, message: str):
        """Send Telegram notification"""
        if not self.notifications['telegram']['enabled']:
            return
        
        try:
            # Format message for Telegram (use Markdown)
            telegram_message = f"🏨 *Hotel Room Alert*\n\n{message}"
            
            payload = {
                "chat_id": self.notifications['telegram']['chat_id'],
                "text": telegram_message,
                "parse_mode": "Markdown",
                "disable_web_page_preview": True
            }
            
            url = f"https://api.telegram.org/bot{self.notifications['telegram']['bot_token']}/sendMessage"
            response = requests.post(url, json=payload, timeout=10)
            response.raise_for_status()
            
            self.logger.info("Telegram notification sent")
        except Exception as e:
            self.logger.error(f"Failed to send Telegram notification: {e}")
    
    def notify_all(self, message: str, subject: str = "Hotel Room Alert"):
        """Send notifications to all configured channels"""
        self.send_email_notification(message, subject)
        self.send_discord_notification(message)
        self.send_slack_notification(message)
        self.send_pushover_notification(message, subject)
        self.send_telegram_notification(message)
    
    def format_notification_message(self, changes: dict) -> str:
        """Format notification message"""
        lines = ["Hotel Availability Update\n"]
        lines.append(f"Check time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"Target dates: {', '.join(self.config['target_dates'])}\n")
        
        if changes['new_available']:
            lines.append("NEW ROOMS AVAILABLE:")
            for room in changes['new_available']:
                lines.append(f"• {room['room']} on {room['date']}: {room['count']} rooms at {room['price']}")
            lines.append("")
        
        if changes['lost_available']:
            lines.append("ROOMS NO LONGER AVAILABLE:")
            for room in changes['lost_available']:
                lines.append(f"• {room['room']} on {room['date']}")
            lines.append("")
        
        if changes['current_available']:
            lines.append("CURRENTLY AVAILABLE:")
            for room in changes['current_available']:
                lines.append(f"• {room['room']} on {room['date']}: {room['count']} rooms at {room['price']}")
        else:
            lines.append("No rooms currently available")
        
        lines.append(f"\nBook now: https://www.489pro.com/asp/489/menu.asp?id={self.config['hotel_id']}&ty=ser")
        
        return "\n".join(lines)
    
    def run_single_check(self):
        """Run a single availability check"""
        self.logger.info("Starting availability check...")
        
        # Get current data
        api_data = self.call_api()
        if not api_data:
            self.logger.error("Failed to get API data")
            return
        
        current_availability = self.analyze_data(api_data)
        
        # Load previous state
        state = self.load_state()
        
        # Detect changes
        changes = self.detect_changes(current_availability, state.get('last_available', []))
        
        # Log current status
        available_count = len(changes['current_available'])
        self.logger.info(f"Found {available_count} available room-date combinations")
        
        # Send notifications if there are changes
        if changes['has_changes']:
            message = self.format_notification_message(changes)
            
            if changes['new_available']:
                subject = f"ROOMS AVAILABLE! {len(changes['new_available'])} new options"
                self.notify_all(message, subject)
                self.logger.info(f"Sent notifications for {len(changes['new_available'])} new rooms")
            elif changes['lost_available']:
                subject = f"Rooms no longer available: {len(changes['lost_available'])} options"
                self.notify_all(message, subject)
                self.logger.info(f"Sent notifications for {len(changes['lost_available'])} lost rooms")
        else:
            self.logger.info("No changes detected")
        
        # Update state
        new_state = {
            'last_available': changes['current_available'],
            'last_check': datetime.now().isoformat(),
            'check_count': state.get('check_count', 0) + 1
        }
        self.save_state(new_state)
        
        # Print summary
        self.print_summary(current_availability, changes)
    
    def print_summary(self, availability: List[RoomAvailability], changes: dict):
        """Print summary of current status"""
        print("\n" + "="*70)
        print("HOTEL AVAILABILITY SUMMARY")
        print("="*70)
        print(f"Check time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Target dates: {', '.join(self.config['target_dates'])}")
        
        available = [r for r in availability if r.status == 'available']
        sold_out = [r for r in availability if r.status == 'sold_out']
        
        if available:
            print(f"\nAVAILABLE ROOMS ({len(available)}):")
            for room in available:
                print(f"  • {room.room_name} on {room.date}: {room.available_count} rooms at {room.price}")
        
        if sold_out:
            print(f"\nSOLD OUT ({len(sold_out)}):")
            for room in sold_out:
                print(f"  • {room.room_name} on {room.date}: {room.price}")
        
        if changes['has_changes']:
            print(f"\nCHANGES DETECTED:")
            if changes['new_available']:
                print(f"  New: {len(changes['new_available'])} rooms")
            if changes['lost_available']:
                print(f"  Lost: {len(changes['lost_available'])} rooms")
        
        print("="*70)
    
    def run_continuous_monitoring(self):
        """Run continuous monitoring loop"""
        self.logger.info("Starting continuous monitoring...")
        self.logger.info(f"Check interval: {self.config['check_interval']} seconds")
        
        while True:
            try:
                self.run_single_check()
                self.logger.info(f"Sleeping for {self.config['check_interval']} seconds...")
                time.sleep(self.config['check_interval'])
            except KeyboardInterrupt:
                self.logger.info("Monitoring stopped by user")
                break
            except Exception as e:
                self.logger.error(f"Error in monitoring loop: {e}")
                time.sleep(60)  # Wait 1 minute before retrying

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Enhanced Hotel Availability Monitor')
    parser.add_argument('--mode', choices=['single', 'monitor'], default='single',
                      help='Run mode: single check or continuous monitoring')
    
    args = parser.parse_args()
    
    monitor = EnhancedHotelMonitor()
    
    if args.mode == 'single':
        monitor.run_single_check()
    else:
        monitor.run_continuous_monitoring()

if __name__ == "__main__":
    main()