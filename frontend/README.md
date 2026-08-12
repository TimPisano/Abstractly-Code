# Lease Abstraction Tool - Frontend

A clean, minimal web interface for extracting lease data from PDF documents.

## Features

- **Drag-and-drop file upload** - Simply drag a PDF onto the upload area
- **Real-time extraction** - See results immediately after upload
- **Detailed source tracking** - Every extracted field shows the page number and exact quote where it was found
- **Clear "not found" indicators** - Fields that couldn't be extracted are clearly marked
- **JSON export** - Download the complete extraction results as JSON
- **Responsive design** - Works on desktop and mobile devices

## How to Run

### Prerequisites

1. **Backend must be running first**. Navigate to the backend directory and start the Flask server:
   ```bash
   cd ../backend
   pip install -r requirements.txt
   python run.py
   ```
   The backend will run on `http://localhost:5000`

2. **A web server for the frontend**. You can use any of these options:

### Option 1: Python's built-in server (simplest)

```bash
cd frontend
python3 -m http.server 8080
```

Then open your browser to `http://localhost:8080`

### Option 2: Node.js http-server

```bash
# Install globally (one time)
npm install -g http-server

# Run from frontend directory
cd frontend
http-server -p 8080
```

Then open your browser to `http://localhost:8080`

### Option 3: VS Code Live Server

1. Install the "Live Server" extension in VS Code
2. Right-click on `index.html` and select "Open with Live Server"

## Usage

1. Start the backend server (see Prerequisites)
2. Start the frontend server (see options above)
3. Open the application in your web browser
4. Upload a lease PDF by either:
   - Clicking the upload box and selecting a file
   - Dragging and dropping a PDF file onto the upload box
5. Wait for processing to complete
6. Review the extracted fields - each shows:
   - The extracted value
   - The page number where it was found
   - A quote showing the context from the PDF
7. Click "Export JSON" to download the complete results

## Technical Details

### Stack
- **Pure vanilla JavaScript** - No frameworks or build tools required
- **Modern CSS** - CSS Grid and Flexbox for layout
- **Semantic HTML5** - Clean, accessible markup

### API Integration
The frontend expects a backend API at `http://localhost:5000` with the following endpoint:

- `POST /extract` - Accepts multipart/form-data with a PDF file
  - Request: `file` field containing the PDF
  - Response: JSON with extracted lease fields and their sources

### File Structure
```
frontend/
├── index.html      # Main HTML structure
├── styles.css      # All styles and theming
├── app.js          # JavaScript logic and API calls
└── README.md       # This file
```

## Extracted Fields

The tool extracts the following lease information:
- Tenant Name
- Monthly Rent
- Lease Start Date
- Lease End Date

Each field includes:
- **Value**: The extracted text
- **Source Page**: Page number where found
- **Source Quote**: Context from the PDF showing where the value was extracted
- **Status**: Whether the field was found or not

Note: The backend can be extended to extract additional fields like landlord name, property address, security deposit, etc.

## Browser Compatibility

Works on all modern browsers:
- Chrome/Edge (recommended)
- Firefox
- Safari

## Troubleshooting

**"Failed to process file" error**
- Make sure the backend server is running on port 5000
- Check browser console for CORS errors
- Verify the PDF file is valid and under 16MB

**Upload doesn't work**
- Ensure you're uploading a PDF file (not another format)
- Check that the file is under 16MB
- Try using the file picker instead of drag-and-drop

**No results displayed**
- Check browser console for JavaScript errors
- Verify the backend is returning data (check Network tab in browser DevTools)
- Make sure the PDF contains recognizable text (not just scanned images)

## Development Notes

The code is intentionally kept simple and well-commented for easy understanding and modification. To customize:

- **Add new fields**: Update the `fieldLabels` object in `app.js`
- **Change styling**: Modify CSS variables in `:root` in `styles.css`
- **Change API endpoint**: Update `API_BASE_URL` in `app.js`
