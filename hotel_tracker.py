#!/usr/bin/env python3
"""
Hotel Availability Tracker for Claude Code
Monitors availability for 489pro.com hotel reservation system

Target dates: October 24-25, 2025
Guests: 2 people
Hotel: Kamikochi area hotel (大正池 Taisho-ike area)
"""

import requests
import time
import json
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Configuration
HOTEL_URL = "https://www.489pro.com/asp/489/menu.asp?id=20000122&ty=ser"
CHECK_IN_DATE = "2025-10-24"
CHECK_OUT_DATE = "2025-10-25" 
GUESTS = 2
CHECK_INTERVAL = 300  # 5 minutes in seconds
MAX_RETRIES = 3

# Email notification settings (optional - configure as needed)
SMTP_SERVER = ""  # e.g., "smtp.gmail.com"
SMTP_PORT = 587
EMAIL_USER = ""
EMAIL_PASS = ""
NOTIFY_EMAIL = ""

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('hotel_availability.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class HotelAvailabilityTracker:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5,ja;q=0.3',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        })
        self.last_status = None
        
    def check_availability(self):
        """
        Check hotel availability for the specified dates
        Returns: dict with availability status and details
        """
        try:
            logger.info(f"Checking availability for {CHECK_IN_DATE} to {CHECK_OUT_DATE} for {GUESTS} guests")
            
            # Get the main reservation page first
            response = self.session.get(HOTEL_URL, timeout=30)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Check if the target dates are already visible
            page_text = soup.get_text()
            if "10/24" in page_text and "10/25" in page_text:
                logger.info("Target dates already visible on current page")
                availability_info = self._parse_availability(soup, page_text)
            else:
                # Try submitting the search form to get to calendar
                calendar_soup = self._submit_search_form(soup)
                if calendar_soup:
                    calendar_text = calendar_soup.get_text()
                    logger.info("Form submitted successfully, checking for calendar endpoint")
                    
                    # Look for calendar JavaScript or direct calendar links
                    calendar_script_url = None
                    page_html = str(calendar_soup)
                    
                    # Look for calendar.asp endpoint
                    if 'calendar.asp' in page_html:
                        import re
                        # Extract the calendar URL pattern
                        calendar_match = re.search(r'calendar\.asp[^"\']*', page_html)
                        if calendar_match:
                            calendar_endpoint = calendar_match.group(0)
                            calendar_script_url = f"https://www.489pro.com/asp/g/c/{calendar_endpoint}"
                            logger.info(f"Found calendar endpoint: {calendar_script_url}")
                    
                    # Also look for stockcalendar initialization
                    if 'initStockCalendarRe' in page_html:
                        logger.info("Found stock calendar JavaScript initialization")
                        
                        # Extract calendar parameters
                        init_match = re.search(r'initStockCalendarRe\([^)]+\)', page_html)
                        if init_match:
                            logger.info(f"Calendar init params: {init_match.group(0)[:200]}...")
                    
                    # Try to build a proper calendar URL with parameters from the JavaScript
                    if 'initStockCalendarRe' in page_html:
                        try:
                            # Extract the JavaScript parameters
                            init_match = re.search(r'initStockCalendarRe\(\s*"([^"]*)"[^,]*,\s*[^,]*,\s*(\d+)[^,]*,\s*[^,]*,\s*"([^"]*)"[^,]*,\s*"([^"]*)"[^,]*,\s*"([^"]*)"', page_html)
                            if init_match:
                                hotel_id = init_match.group(1)  # "20000122"
                                user_num = init_match.group(2)  # "2"
                                start_date = init_match.group(3)  # "2025/8/26"
                                end_date = init_match.group(4)  # "2025/9/1"
                                params = init_match.group(5)  # The parameter string
                                
                                logger.info(f"Parsed calendar params: hotel_id={hotel_id}, users={user_num}, dates={start_date} to {end_date}")
                                
                                # Build calendar URL with proper parameters
                                # Based on the JavaScript, we need these parameters
                                calendar_url = f"https://www.489pro.com/asp/g/c/calendar.asp?kid={hotel_id}&lan=JPN"
                                
                                logger.info(f"Attempting to access calendar with parameters: {calendar_url}")
                                cal_response = self.session.get(calendar_url, timeout=30)
                                cal_response.raise_for_status()
                                
                                if cal_response.text.strip() != "Not Found":
                                    calendar_soup = BeautifulSoup(cal_response.content, 'html.parser')
                                    calendar_text = calendar_soup.get_text()
                                    logger.info("Successfully accessed calendar with parameters")
                                    
                                    # Save debug file for the actual calendar
                                    with open('debug_actual_calendar.html', 'w', encoding='utf-8') as f:
                                        f.write(str(calendar_soup))
                                    logger.info("Saved actual calendar content to debug_actual_calendar.html")
                                    
                                    # Check what dates are actually displayed
                                    import re
                                    dates_in_cal = re.findall(r'\d{1,2}/\d{1,2}', calendar_text)
                                    logger.info(f"Dates found in calendar: {dates_in_cal}")
                                else:
                                    logger.warning("Calendar endpoint returned 'Not Found'")
                            
                        except Exception as e:
                            logger.warning(f"Could not parse calendar parameters or access calendar: {e}")
                    
                    if "10/24" in calendar_text and "10/25" in calendar_text:
                        logger.info("Target dates found after form submission")
                        availability_info = self._parse_availability(calendar_soup, calendar_text)
                    else:
                        logger.info("Target dates not visible, need to navigate from calendar page")
                        # Navigate from the calendar page
                        nav_soup, nav_url = self.navigate_to_target_month(CHECK_IN_DATE, calendar_soup, response.url)
                        if nav_soup:
                            availability_info = self._parse_availability(nav_soup, nav_soup.get_text())
                        else:
                            availability_info = self._parse_availability(calendar_soup, calendar_text)
                else:
                    logger.info("Target dates not visible on main page, looking for calendar link")
                
                # Look for links that might lead to the calendar/availability page
                calendar_keywords = ['空室', '予約', 'カレンダー', '宿泊', 'reservation', 'calendar', 'availability']
                potential_links = []
                
                for link in soup.find_all('a', href=True):
                    link_text = link.get_text().strip()
                    link_href = link['href']
                    
                    # Check if link text contains calendar-related keywords
                    for keyword in calendar_keywords:
                        if keyword in link_text or keyword in link_href:
                            potential_links.append((link_text, link_href))
                            break
                
                logger.info(f"Found potential calendar links: {potential_links}")
                
                # Try each promising link until we find one with a calendar
                calendar_found = False
                for link_text, calendar_url in potential_links:
                    if not calendar_url.startswith('http'):
                        from urllib.parse import urljoin
                        calendar_url = urljoin(HOTEL_URL, calendar_url)
                    
                    # Skip if it's the same URL we already have
                    if calendar_url == HOTEL_URL:
                        continue
                    
                    logger.info(f"Trying calendar URL: {calendar_url} ({link_text})")
                    try:
                        response = self.session.get(calendar_url, timeout=30)
                        response.raise_for_status()
                        soup = BeautifulSoup(response.content, 'html.parser')
                        
                        # Check if this page has calendar elements
                        page_text = soup.get_text()
                        has_calendar_indicators = ('カレンダー' in page_text or 
                                                 '空室' in page_text or 
                                                 '○' in page_text or 
                                                 '×' in page_text or 
                                                 '後の期間' in page_text)
                        
                        logger.info(f"Page has calendar indicators: {has_calendar_indicators}")
                        
                        if "10/24" in page_text and "10/25" in page_text:
                            logger.info("Found target dates on calendar page")
                            availability_info = self._parse_availability(soup, page_text)
                            calendar_found = True
                            break
                        elif has_calendar_indicators:
                            logger.info("Found calendar page, attempting navigation")
                            # Navigate from this calendar page
                            soup, current_url = self.navigate_to_target_month(CHECK_IN_DATE)
                            if soup is not None:
                                availability_info = self._parse_availability(soup, soup.get_text())
                                calendar_found = True
                                break
                        else:
                            logger.info("Page doesn't appear to have calendar, trying next link")
                            
                    except Exception as e:
                        logger.warning(f"Failed to access calendar URL {calendar_url}: {e}")
                        continue
                
                if not calendar_found:
                    # Navigate from the original page
                    soup, current_url = self.navigate_to_target_month(CHECK_IN_DATE, soup, response.url)
                
                if soup is None:
                    logger.warning("Navigation failed, using original page")
                    # Re-get the original page soup since navigation failed  
                    response = self.session.get(HOTEL_URL, timeout=30)
                    response.raise_for_status()
                    soup = BeautifulSoup(response.content, 'html.parser')
                    availability_info = self._parse_availability(soup, soup.get_text())
                else:
                    availability_info = self._parse_availability(soup, soup.get_text())
            
            return availability_info
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Request failed: {e}")
            return {"status": "error", "message": str(e)}
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            return {"status": "error", "message": str(e)}
    
    def _submit_search_form(self, soup):
        """Submit the search form to access the calendar page"""
        try:
            # Find the form with the search button
            forms = soup.find_all('form')
            for form in forms:
                inputs = form.find_all('input')
                # Look for form with the search button
                search_button = None
                for inp in inputs:
                    if inp.get('value') and 'この条件で空室状況を表示' in inp.get('value'):
                        search_button = inp
                        break
                
                if search_button:
                    logger.info("Found availability search form")
                    
                    # Get form action and method
                    action = form.get('action', '')
                    method = form.get('method', 'GET').upper()
                    
                    # Build form data
                    form_data = {}
                    for inp in inputs:
                        name = inp.get('name')
                        value = inp.get('value', '')
                        if name:
                            form_data[name] = value
                    
                    # Set our target dates (October 24, 2025)
                    # Based on the form structure we saw: year, month, day
                    from datetime import datetime
                    target_dt = datetime.strptime(CHECK_IN_DATE, "%Y-%m-%d")
                    
                    # Update form data with our target check-in date
                    for key, val in form_data.items():
                        if 'year' in key.lower() or (key and '2025' in str(val)):
                            form_data[key] = str(target_dt.year)
                        elif 'month' in key.lower() or (key and val in ['8', '9', '10', '11', '12']):
                            form_data[key] = str(target_dt.month)
                        elif 'day' in key.lower() or (key and val in ['26', '27', '28', '29', '30', '31']):
                            form_data[key] = str(target_dt.day)
                    
                    logger.info(f"Submitting search form with data: {form_data}")
                    
                    # Submit the form
                    if action:
                        if not action.startswith('http'):
                            from urllib.parse import urljoin
                            action = urljoin(HOTEL_URL, action)
                        
                        if method == 'POST':
                            response = self.session.post(action, data=form_data, timeout=30)
                        else:
                            response = self.session.get(action, params=form_data, timeout=30)
                        
                        response.raise_for_status()
                        return BeautifulSoup(response.content, 'html.parser')
            
            logger.warning("Could not find availability search form")
            return None
            
        except Exception as e:
            logger.error(f"Error submitting search form: {e}")
            return None
    
    def navigate_to_target_month(self, target_date, initial_soup=None, base_url=None):
        """
        Navigate through calendar periods to reach target month
        target_date should be in format "2024-10-24"
        """
        from datetime import datetime
        target_dt = datetime.strptime(target_date, "%Y-%m-%d")
        target_month = target_dt.month
        target_year = target_dt.year
        
        current_url = base_url or HOTEL_URL
        max_clicks = 15  # Safety limit - we need about 8 clicks from current date
        clicks = 0
        soup = initial_soup  # Start with provided soup if available
        
        while clicks < max_clicks:
            try:
                # Use provided soup for first iteration, then fetch for subsequent ones
                if soup is None or clicks > 0:
                    response = self.session.get(current_url, timeout=30)
                    response.raise_for_status()
                    soup = BeautifulSoup(response.content, 'html.parser')
                
                # Check if we're in the right month/year by looking for dates
                date_headers = soup.find_all('td', string=lambda x: x and any(char.isdigit() for char in str(x)))
                current_period_info = self._extract_current_period(soup)
                
                logger.info(f"Current period: {current_period_info}")
                
                # If we found our target month, return the soup
                if self._is_target_month_displayed(soup, target_month, target_year):
                    logger.info(f"Found target month after {clicks} clicks")
                    return soup, current_url
                
                # Look for "後の期間" (next period) button/link - try multiple approaches
                next_period_link = soup.find('a', string='後の期間') or soup.find('input', {'value': '後の期間'})
                if not next_period_link:
                    # Try alternative selectors
                    next_period_link = soup.find('a', title='後の期間') or soup.find('input', {'type': 'submit', 'value': '後の期間'})
                    
                if not next_period_link:
                    # Try looking for any element containing the text
                    all_elements = soup.find_all(string=lambda x: x and '後の期間' in str(x))
                    if all_elements:
                        for element in all_elements:
                            parent = element.parent
                            if parent and parent.name in ['a', 'input', 'button']:
                                next_period_link = parent
                                break
                
                # Debug: print what navigation elements we can find
                nav_elements = soup.find_all(['a', 'input', 'button'])
                nav_texts = [elem.get_text().strip() for elem in nav_elements if elem.get_text().strip()]
                logger.info(f"Available navigation elements: {nav_texts[:10]}...")  # Show first 10
                
                # Also look for any clickable elements containing the navigation text
                all_text_elements = soup.find_all(string=True)
                period_related = [elem for elem in all_text_elements if '期間' in str(elem) or '後の' in str(elem)]
                logger.info(f"Elements containing '期間' or '後の': {period_related}")
                
                # Look for forms that might contain the navigation
                forms = soup.find_all('form')
                logger.info(f"Found {len(forms)} forms on page")
                for i, form in enumerate(forms):
                    form_inputs = form.find_all(['input', 'button'])
                    form_input_values = [inp.get('value', inp.get_text()) for inp in form_inputs]
                    logger.info(f"Form {i} inputs/buttons: {form_input_values}")
                
                # Look for any input with value containing navigation text
                all_inputs = soup.find_all('input')
                for inp in all_inputs:
                    val = inp.get('value', '')
                    if '期間' in val or '後の' in val:
                        logger.info(f"Found navigation input: {inp}")
                        next_period_link = inp
                        break
                
                if next_period_link:
                    if next_period_link.name == 'a' and 'href' in next_period_link.attrs:
                        # It's a link
                        next_url = next_period_link['href']
                        if not next_url.startswith('http'):
                            from urllib.parse import urljoin
                            next_url = urljoin(current_url, next_url)
                        current_url = next_url
                    else:
                        # It might be a form submission - need to handle forms
                        form = next_period_link.find_parent('form')
                        if form:
                            action = form.get('action', current_url)
                            if not action.startswith('http'):
                                from urllib.parse import urljoin
                                action = urljoin(current_url, action)
                            
                            # Collect form data
                            form_data = {}
                            for input_elem in form.find_all('input'):
                                if input_elem.get('name'):
                                    form_data[input_elem['name']] = input_elem.get('value', '')
                            
                            response = self.session.post(action, data=form_data, timeout=30)
                            current_url = response.url
                        else:
                            logger.warning("Could not determine how to navigate to next period")
                            break
                    
                    clicks += 1
                    time.sleep(1)  # Be polite to the server
                else:
                    logger.warning("No 'next period' button found")
                    break
                    
            except Exception as e:
                logger.error(f"Error navigating calendar: {e}")
                break
        
        logger.warning(f"Could not reach target month after {clicks} attempts")
        return None, current_url
    
    def _extract_current_period(self, soup):
        """Extract information about current period being displayed"""
        # Look for date headers or month indicators
        date_cells = soup.find_all('td', string=lambda x: x and '/' in str(x))
        if date_cells:
            return [cell.get_text().strip() for cell in date_cells[:3]]
        
        # Also look for any text containing dates
        page_text = soup.get_text()
        import re
        date_matches = re.findall(r'\d{1,2}/\d{1,2}', page_text)
        if date_matches:
            return f"Found dates: {date_matches[:5]}"
        
        return "Unknown period"
    
    def _is_target_month_displayed(self, soup, target_month, target_year):
        """Check if the target month/year is currently displayed"""
        page_text = soup.get_text()
        
        # Look for our specific target dates 10/24 and 10/25
        target_dates = ["10/24", "10/25"]
        
        # Check if any of our target dates are visible
        for date in target_dates:
            if date in page_text:
                logger.info(f"Found target date {date} in page")
                return True
        
        # Also check for October month indicator
        if target_month == 10 and ("10月" in page_text or "10/" in page_text):
            return True
            
        return False
    
    def _parse_availability(self, soup, page_text):
        """
        Parse the calendar table to find availability for target dates
        Looking for ○ (available), × (full), - (not bookable) symbols
        """
        availability_info = {
            "timestamp": datetime.now().isoformat(),
            "status": "unknown",
            "details": {},
            "room_availability": {},
            "target_dates_found": False
        }
        
        # Debug: Check what's actually on the page
        logger.info(f"Page contains 10/24: {'10/24' in page_text}")
        logger.info(f"Page contains 10/25: {'10/25' in page_text}")
        logger.info(f"Page contains ○: {'○' in page_text}")
        logger.info(f"Page contains ×: {'×' in page_text}")
        
        # Find the availability table
        table = soup.find('table')
        if not table:
            # Look for any table-like structure
            table = soup.find('div', class_=lambda x: x and 'calendar' in x.lower()) or soup.find('div', class_=lambda x: x and 'table' in x.lower())
        
        if not table:
            # If no table found, still check for availability indicators in the text
            availability_info["status"] = "no_calendar_found"
            availability_info["page_contains_target_dates"] = "10/24" in page_text and "10/25" in page_text
            availability_info["page_contains_symbols"] = {"circle": "○" in page_text, "cross": "×" in page_text}
            return availability_info
        
        # Look for date headers in the table
        date_headers = []
        rows = table.find_all('tr')
        
        # Find the header row with dates
        for row in rows:
            cells = row.find_all(['th', 'td'])
            row_dates = []
            for cell in cells:
                cell_text = cell.get_text().strip()
                # Look for date patterns like 10/24, 10/25 etc
                if '/' in cell_text and any(char.isdigit() for char in cell_text):
                    row_dates.append(cell_text)
            
            # If we found multiple dates in this row, it's likely the header
            if len(row_dates) >= 2:
                date_headers = row_dates
                break
        
        logger.info(f"Found date headers: {date_headers}")
        
        # If no date headers found in table, look in the entire page
        if not date_headers:
            import re
            all_dates = re.findall(r'\d{1,2}/\d{1,2}', page_text)
            logger.info(f"All dates found in page text: {all_dates}")
            
            # Look specifically for our target dates in the page
            target_dates_in_text = []
            if "10/24" in page_text:
                target_dates_in_text.append("10/24")
            if "10/25" in page_text:
                target_dates_in_text.append("10/25")
            
            if target_dates_in_text:
                logger.info(f"Target dates found in page text: {target_dates_in_text}")
                availability_info["target_dates_found"] = True
                # Try to find room availability even without clear table structure
                room_types = re.findall(r'([^\n]*室[^\n]*)', page_text)
                logger.info(f"Potential room types found: {room_types[:5]}")  # Show first 5
        
        # Find target date columns (looking for 10/24, 10/25)
        target_date_indices = []
        for i, header in enumerate(date_headers):
            if "10/24" in header or "10/25" in header:
                target_date_indices.append(i + 1)  # +1 because first column is typically room type
                availability_info["target_dates_found"] = True
                logger.info(f"Found target date {header} at column index {i+1}")
        
        if not target_date_indices and not availability_info["target_dates_found"]:
            availability_info["status"] = "target_dates_not_in_period"
            availability_info["current_period"] = date_headers
            return availability_info
        
        # If we found target dates in text but no clear table structure, try text-based parsing
        if not target_date_indices and availability_info["target_dates_found"]:
            logger.info("Attempting text-based availability parsing")
            return self._parse_availability_from_text(page_text)
        
        logger.info(f"Target date columns found at indices: {target_date_indices}")
        
        # Parse room availability
        rows = table.find_all('tr')[1:]  # Skip header row
        
        for row in rows:
            cells = row.find_all(['td', 'th'])
            if len(cells) > max(target_date_indices):
                # Get room type (first column)
                room_type = cells[0].get_text().strip()
                
                if room_type and "室" in room_type:  # Only process actual room rows
                    room_availability = {}
                    
                    for date_idx in target_date_indices:
                        if date_idx < len(cells):
                            cell = cells[date_idx]
                            cell_text = cell.get_text().strip()
                            
                            # Check for availability symbols
                            if "○" in cell_text:
                                status = "available"  # ○：空室あり
                            elif "×" in cell_text:
                                status = "full"       # ×：満室
                            elif "-" in cell_text:
                                status = "not_bookable"  # -：設定なし
                            else:
                                status = "unknown"
                            
                            logger.info(f"Room {room_type}, Date column {date_idx}: '{cell_text}' -> {status}")
                            
                            # Extract price if present
                            price = None
                            if "円" in cell_text:
                                import re
                                price_match = re.search(r'([\d,]+)円', cell_text)
                                if price_match:
                                    price = price_match.group(1)
                            
                            date_header = date_headers[date_idx - 1] if date_idx - 1 < len(date_headers) else f"col_{date_idx}"
                            room_availability[date_header] = {
                                "status": status,
                                "price": price,
                                "raw_text": cell_text
                            }
                    
                    if room_availability:
                        availability_info["room_availability"][room_type] = room_availability
        
        # Determine overall status
        if availability_info["room_availability"]:
            available_rooms = []
            for room_type, dates in availability_info["room_availability"].items():
                for date, info in dates.items():
                    if info["status"] == "available":
                        available_rooms.append(f"{room_type} on {date}")
            
            if available_rooms:
                availability_info["status"] = "available"
                availability_info["available_rooms"] = available_rooms
            else:
                availability_info["status"] = "no_availability"
        
        return availability_info
    
    def _parse_availability_from_text(self, page_text):
        """Parse availability from page text when table structure is unclear"""
        availability_info = {
            "timestamp": datetime.now().isoformat(),
            "status": "unknown",
            "details": {},
            "room_availability": {},
            "target_dates_found": True,
            "parsing_method": "text_based"
        }
        
        # Look for availability indicators near our target dates
        lines = page_text.split('\n')
        for i, line in enumerate(lines):
            # Look for lines containing room types and dates
            if ('室' in line or 'ルーム' in line) and ('10/24' in line or '10/25' in line):
                logger.info(f"Found potential room availability line: {line.strip()}")
                
                # Look for availability symbols in surrounding lines
                context_lines = lines[max(0, i-2):i+3]  # Get surrounding context
                context_text = ' '.join(context_lines)
                
                room_type = line.strip()
                availability_info["room_availability"][room_type] = {
                    "10/24": {"status": "unknown", "context": context_text},
                    "10/25": {"status": "unknown", "context": context_text}
                }
                
                # Check for availability symbols in context
                if '○' in context_text:
                    availability_info["room_availability"][room_type]["10/24"]["status"] = "available"
                    availability_info["room_availability"][room_type]["10/25"]["status"] = "available"
                elif '×' in context_text:
                    availability_info["room_availability"][room_type]["10/24"]["status"] = "full"
                    availability_info["room_availability"][room_type]["10/25"]["status"] = "full"
        
        # Set overall status
        if availability_info["room_availability"]:
            available_count = sum(1 for room_data in availability_info["room_availability"].values() 
                                for date_data in room_data.values() 
                                if isinstance(date_data, dict) and date_data.get("status") == "available")
            if available_count > 0:
                availability_info["status"] = "available"
                availability_info["details"]["available_rooms_dates"] = available_count
            else:
                availability_info["status"] = "no_availability"
        else:
            availability_info["status"] = "target_dates_found_but_no_rooms_parsed"
        
        return availability_info
    
    def send_notification(self, availability_info):
        """Send email notification if configured"""
        if not all([SMTP_SERVER, EMAIL_USER, EMAIL_PASS, NOTIFY_EMAIL]):
            logger.info("Email notification not configured")
            return
        
        try:
            msg = MIMEMultipart()
            msg['From'] = EMAIL_USER
            msg['To'] = NOTIFY_EMAIL
            msg['Subject'] = f"Hotel Availability Update - {availability_info['status']}"
            
            body = f"""
            Hotel Availability Update
            
            Date/Time: {availability_info['timestamp']}
            Check-in: {CHECK_IN_DATE}
            Check-out: {CHECK_OUT_DATE}
            Guests: {GUESTS}
            
            Status: {availability_info['status']}
            
            Details: {json.dumps(availability_info['details'], indent=2)}
            
            URL: {HOTEL_URL}
            """
            
            msg.attach(MIMEText(body, 'plain'))
            
            server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
            server.starttls()
            server.login(EMAIL_USER, EMAIL_PASS)
            text = msg.as_string()
            server.sendmail(EMAIL_USER, NOTIFY_EMAIL, text)
            server.quit()
            
            logger.info("Notification email sent")
        except Exception as e:
            logger.error(f"Failed to send email notification: {e}")
    
    def run_continuous_monitoring(self):
        """Run continuous monitoring loop"""
        logger.info("Starting hotel availability monitoring...")
        logger.info(f"Target: {CHECK_IN_DATE} to {CHECK_OUT_DATE} for {GUESTS} guests")
        logger.info(f"Check interval: {CHECK_INTERVAL} seconds")
        
        while True:
            try:
                availability = self.check_availability()
                
                # Log current status
                logger.info(f"Status: {availability['status']}")
                
                # Check if status changed
                if self.last_status != availability['status']:
                    logger.info(f"Status changed from {self.last_status} to {availability['status']}")
                    self.send_notification(availability)
                    self.last_status = availability['status']
                
                # Save to file for persistence
                with open('latest_availability.json', 'w') as f:
                    json.dump(availability, f, indent=2)
                
                # Wait before next check
                time.sleep(CHECK_INTERVAL)
                
            except KeyboardInterrupt:
                logger.info("Monitoring stopped by user")
                break
            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")
                time.sleep(60)  # Wait 1 minute before retrying
    
    def single_check(self):
        """Perform a single availability check"""
        availability = self.check_availability()
        print(json.dumps(availability, indent=2))
        return availability

def main():
    """Main function"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Hotel Availability Tracker')
    parser.add_argument('--mode', choices=['single', 'monitor'], default='single',
                      help='Run mode: single check or continuous monitoring')
    
    args = parser.parse_args()
    
    tracker = HotelAvailabilityTracker()
    
    if args.mode == 'single':
        tracker.single_check()
    else:
        tracker.run_continuous_monitoring()

if __name__ == "__main__":
    main()
