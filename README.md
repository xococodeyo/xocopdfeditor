# Xcoco PDF Editor

Are you tired of searching for PDF editors that are either paid, have limited free use, or add annoying watermarks?
Me too!

That's why I created this project with a coding vibe.

A simple PDF editor you can freely use and adapt. It basically allows you to do just two things:

Add text to the PDF

Add images to the PDF

It also includes options to load a PDF, download the edited version, zoom in/out, and undo your last action.

Feel free to use it!

---

A simple PDF editor built with Python, Tkinter, and PyMuPDF (fitz). This application allows you to open PDF files, add images and text, and save the changes to a new PDF.

## Features

- **Open and Display PDFs**: Load and view multi-page PDF documents.
- **Add Images**: Place PNG images anywhere on a page by drawing a rectangle.
- **Add Text**: Add text with customizable font, size, and color.
- **Zoom Functionality**: Zoom in and out for a better view of the document.
- **Undo**: Revert the last action (adding an image or text).
- **Save as New PDF**: Save all your edits into a new PDF file without modifying the original.
- **Cross-platform**: Works on macOS, Windows, and Linux.

## Prerequisites

- Python 3.x
- `pip` package manager

## Installation

1.  **Clone the repository:**
    ```bash
    git clone <repository_url>
    cd pdfeditor
    ```

2.  **Create and activate a virtual environment:**
    *   **macOS/Linux:**
        ```bash
        python3 -m venv venv
        source venv/bin/activate
        ```
    *   **Windows:**
        ```bash
        python -m venv venv
        .\venv\Scripts\activate
        ```

3.  **Install the required packages:**
    ```bash
    pip install -r requirements.txt
    ```

## Usage

Run the application with the following command:

```bash
python pdf_editor.py
```

- Use **File > Open PDF** to load a document.
- Use the **Edit** menu to add images or text.
- Use the **View** menu or `Ctrl/Cmd` + `+`/`-` to zoom.
- Use **Edit > Undo** or `Ctrl/Cmd` + `Z` to undo the last change.
- Use **File > Save PDF As...** to save your work.

## Project Structure

- `pdf_editor.py`: The main application script containing all the logic.
- `requirements.txt`: A list of Python dependencies for the project.
- `.gitignore`: Specifies intentionally untracked files to ignore.
- `README.md`: This file.
