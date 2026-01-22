# Architecture Page Fix - Instructions

## Issue
The architecture page was stuck on "Loading architecture documentation..." because the markdown files weren't being served by the Flask backend.

## Solution Implemented

1. **Created new Flask route** (`webapp/backend/routes/architecture.py`):
   - `/api/architecture/docs/<filename>` - Serves markdown files
   - `/api/architecture/diagram/<filename>` - Serves diagram images
   - `/api/architecture/list` - Lists available files

2. **Updated Flask app** (`webapp/backend/app.py`):
   - Registered new architecture blueprint

3. **Updated JavaScript** (`webapp/frontend/js/architecture.js`):
   - Changed to use API endpoints instead of direct file access
   - Better error handling with helpful messages

## How to Apply the Fix

### Step 1: Restart the Web Application

```bash
# Stop the current web server (Ctrl+C in the terminal where it's running)
# Then restart:
cd /Users/harriskhalid/Desktop/Red_Team_Infra/webapp
./start.sh
```

### Step 2: Verify the Fix

1. Open browser: `http://localhost:5000/architecture.html`
2. You should now see:
   - Architecture dropdown selector
   - Diagram automatically loads
   - Documentation renders below diagram

### Step 3: Test All Architecture Types

Try selecting each option from the dropdown:
- ✅ GOAD Mini - Should show diagram + full documentation
- ✅ GOAD Light - Should show diagram + documentation
- ✅ C2 Ad-Hoc - Should show diagram + documentation
- ✅ All other types - Should work properly

## What Changed

### Before (Broken):
```javascript
// Tried to fetch files directly - doesn't work with Flask
fetch('../../docs/architectures/goad-mini.md')
```

### After (Fixed):
```javascript
// Uses Flask API endpoint - works correctly
fetch('/api/architecture/docs/goad-mini.md')
```

## Troubleshooting

### If still stuck on loading:

1. **Check web server is running**:
   ```bash
   ps aux | grep python | grep app.py
   ```

2. **Check Flask logs** in the terminal for errors

3. **Hard refresh browser**:
   - Chrome/Firefox: `Ctrl+Shift+R` (Windows/Linux) or `Cmd+Shift+R` (Mac)
   - This clears cached JavaScript

4. **Check API endpoint manually**:
   ```bash
   curl http://localhost:5000/api/architecture/docs/goad-mini.md
   # Should return JSON with content
   ```

5. **Verify files exist**:
   ```bash
   ls -la /Users/harriskhalid/Desktop/Red_Team_Infra/docs/architectures/
   ls -la /Users/harriskhalid/Desktop/Red_Team_Infra/generated-diagrams/
   ```

## Expected Behavior

After the fix:
1. **Page loads** - Shows dropdown and "Loading..." message
2. **API call** - JavaScript fetches markdown from Flask
3. **Diagram loads** - PNG served via Flask API
4. **Documentation renders** - Markdown converted to HTML
5. **All functional** - Can switch between architecture types

## Files Modified

- ✅ `webapp/backend/routes/architecture.py` (NEW)
- ✅ `webapp/backend/app.py` (UPDATED)
- ✅ `webapp/frontend/js/architecture.js` (UPDATED)

## Next Steps

After restarting the web server, everything should work perfectly! You'll be able to:
- View all 13 architecture types
- See AWS diagrams generated with MCP
- Read comprehensive documentation
- Click diagrams to view full size
- Navigate between different deployments

Enjoy exploring the architecture documentation! 🎉
