# Web Application Quick Start

## Starting the Web Application

### Method 1: Using Start Script (Easiest)

```bash
cd Red_Team_Infra
./webapp/start.sh
```

The script will:
1. Create Python virtual environment (if needed)
2. Install all dependencies
3. Start the web server
4. Display the URL to access

### Method 2: Manual Start

```bash
# Install dependencies
pip install -r requirements.txt

# Start the application
cd Red_Team_Infra
python3 webapp/backend/app.py
```

## Accessing the Application

Once started, open your web browser and navigate to:

**http://127.0.0.1:5000**

The application runs on **localhost only** for security.

## First Steps

1. **Check Prerequisites** (Health tab)
   - Verify all tools are installed
   - Check AWS connectivity

2. **Configure Infrastructure** (Configuration tab)
   - Select engagement type
   - Fill in required fields
   - Save configuration

3. **Deploy** (Deploy tab)
   - Run plan to preview changes
   - Deploy infrastructure
   - Monitor progress

4. **Monitor** (Status tab)
   - View infrastructure status
   - Check outputs
   - View resources

## Troubleshooting

### Port Already in Use
Change the port in `webapp/backend/app.py`:
```python
app.run(host='127.0.0.1', port=5001)  # Change to different port
```

### Dependencies Missing
```bash
pip install -r requirements.txt
```

### Application Won't Start
Check that you're in the project root directory and all files are present.

