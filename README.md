# Hotel Availability Monitor

Automated hotel room availability monitoring using GitHub Actions. Monitors specific dates and sends notifications when rooms become available.

## Features

- **Automated Monitoring**: Runs every 5 minutes via GitHub Actions
- **Multiple Notifications**: Email, Discord, Slack, Pushover
- **State Tracking**: Detects new availability and changes
- **API-Based**: Uses hotel's API for accurate, real-time data
- **Free & Reliable**: Runs on GitHub's free tier

## Quick Setup

### 1. Fork/Clone Repository

```bash
git clone https://github.com/yourusername/hotel-tracker
cd hotel-tracker
```

### 2. Configure GitHub Secrets

Go to your repository → Settings → Secrets and variables → Actions, then add:

**Required for Email Notifications:**
- `EMAIL_USER`: Your Gmail address
- `EMAIL_PASS`: App-specific password (not your regular password)
- `NOTIFY_EMAIL`: Where to send alerts
- `SMTP_SERVER`: `smtp.gmail.com` 
- `SMTP_PORT`: `587`

**Optional Additional Notifications:**
- `DISCORD_WEBHOOK`: Discord webhook URL
- `SLACK_WEBHOOK`: Slack webhook URL  
- `PUSHOVER_TOKEN`: Pushover app token
- `PUSHOVER_USER`: Pushover user key

### 3. Configure Target Dates

Edit `enhanced_monitor.py` line 30 to set your target dates:

```python
'target_dates': ['2025-10-24', '2025-10-25'],  # Your desired dates
```

### 4. Enable GitHub Actions

1. Go to your repository → Actions tab
2. Click "I understand my workflows, go ahead and enable them"
3. The monitor will start running automatically every 5 minutes

## Email Setup (Gmail)

### 1. Enable 2-Factor Authentication
- Go to your Google Account settings
- Enable 2-factor authentication

### 2. Generate App Password
- Go to Google Account → Security → App passwords
- Generate password for "Mail"
- Use this as `EMAIL_PASS` secret (not your regular password)

### 3. Test Email Setup

Run locally to test:

```bash
export EMAIL_USER="your.email@gmail.com"
export EMAIL_PASS="your-app-password"
export NOTIFY_EMAIL="recipient@email.com"
export SMTP_SERVER="smtp.gmail.com"
export SMTP_PORT="587"

python enhanced_monitor.py --mode single
```

## Manual Testing

Test the monitor locally:

```bash
# Install dependencies
pip install -r requirements.txt

# Single check
python enhanced_monitor.py --mode single

# Continuous monitoring (for testing)
python enhanced_monitor.py --mode monitor
```

## How It Works

1. **API Integration**: Calls the hotel's availability API
2. **Data Analysis**: Parses room availability and pricing
3. **Change Detection**: Compares with previous state
4. **Multi-Channel Alerts**: Sends notifications when rooms become available
5. **State Persistence**: Tracks changes between runs

## Monitoring Details

- **Check Frequency**: Every 5 minutes
- **Target Hotel**: Kamikochi Taisho-ike Hotel (ID: 20000122)
- **Room Types**: All available room types
- **Dates**: October 24-25, 2025 (configurable)

## Notification Examples

**New Availability Alert:**
```
ROOMS AVAILABLE! 2 new options

Check time: 2025-08-26 15:30:25
Target dates: 2025-10-24, 2025-10-25

NEW ROOMS AVAILABLE:
• Superior Twin on 2025-10-24: 1 rooms at ¥12,000
• Standard Double on 2025-10-25: 2 rooms at ¥10,000

Book now: https://www.489pro.com/asp/489/menu.asp?id=20000122&ty=ser
```

## Troubleshooting

### Email Not Working
- Verify app password (not regular password)
- Check 2FA is enabled
- Test with simple email client first

### GitHub Actions Failing
- Check repository secrets are set
- Verify workflow file syntax
- Check Actions tab for error logs

### No Notifications Received  
- Run single check locally to verify configuration
- Check spam folder
- Verify webhook URLs are correct

## File Structure

```
hotel-tracker/
├── .github/workflows/monitor.yml  # GitHub Actions workflow
├── enhanced_monitor.py            # Main monitoring script
├── requirements.txt               # Python dependencies  
├── README.md                      # This file
├── monitor_state.json            # State tracking (auto-created)
└── hotel_monitor.log             # Log file (auto-created)
```

## Cost & Limits

- **GitHub Actions**: 2,000 minutes/month free
- **Usage**: ~2 minutes/day = ~60 minutes/month
- **Cost**: Free for typical usage

## Advanced Configuration

Edit `enhanced_monitor.py` to customize:

- Hotel ID and plan ID
- Check intervals  
- Target dates
- API parameters
- Notification formatting

## Privacy & Security

- No room booking performed automatically
- Only checks availability  
- Hotel API is read-only
- GitHub secrets are encrypted
- No personal data stored

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

## Support

Create an issue in this repository with:
- Error messages
- Configuration details (without secrets)
- Expected vs actual behavior