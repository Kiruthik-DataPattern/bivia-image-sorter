# AI Image Sorter (Powered by Articul8 Bivia)

An intelligent, context-aware image classification and sorting application built with Python. It analyzes visual contents using **Articul8 Bivia**'s multimodal decision model (`api.articul8.ai/bivia/decide`) and automatically organizes files into corresponding folders.

---

## 🔑 API Key & Configuration

Your API key is saved in [`image_sorter/.env`](file:///c:/Users/Kiruthik%20Kumar/Project/Figma/image_sorter/.env):

```env
A8_API_KEY=your_articul8_api_key_here
A8_API_URL=https://api.articul8.ai/bivia/decide
A8_MODEL=dec-1
```

*(Note: `.env` is ignored by git via `.gitignore` to prevent leaking credentials).*

---

## 🖥️ Desktop Folders Setup (`Raw_Images` & `Sorted_Images`)

Two folders have been configured on your **Desktop**:

1. [**`Desktop/Raw_Images`**](file:///C:/Users/Kiruthik%20Kumar/Desktop/Raw_Images): Contains the 120 raw mixed-up industrial images (`raw_image_001.jpg` to `raw_image_120.jpg`).
2. [**`Desktop/Sorted_Images`**](file:///C:/Users/Kiruthik%20Kumar/Desktop/Sorted_Images): **Completely empty** (0 files, 0 subfolders) prior to running the script.

### One-Click Desktop Sort:
Double-click [**`run_desktop_sort.bat`**](file:///c:/Users/Kiruthik%20Kumar/Project/Figma/run_desktop_sort.bat) in the project root.

The script will:
1. Ensure `Desktop/Sorted_Images` is strictly empty before beginning.
2. Read the raw mixed images from `Desktop/Raw_Images`.
3. Use the Articul8 Bivia multimodal model to categorize every image.
4. Automatically create the respective subfolders (`pressure_vessel_heavy_equipment`, `piping_valves_manifolds`, `quality_ndt_weld_defects`, `safety_ppe_hazards`, `technical_engineering_drawings`, `other`) inside `Desktop/Sorted_Images` and organize all images into them.

---

## 🖥️ Launching the Native Python Desktop GUI (Tkinter)

The application includes a fully native desktop window built using Python standard library GUI (`tkinter` + `PIL.ImageTk`):

### Option 1: Double-Click Launcher
Double-click [**`run_desktop_ui.bat`**](file:///c:/Users/Kiruthik%20Kumar/Project/Figma/run_desktop_ui.bat) from the workspace root or inside `image_sorter/`.

### Option 2: Command Line
```powershell
cd "image_sorter"
python gui.py
```

### Native Desktop GUI Features:
- **Zero Extra Dependencies**: Runs directly on Python's built-in `tkinter` and `Pillow`.
- **Integrated Live Image Preview**: Click any image in the staged queue to view resolution, file size, and high-quality scaled preview.
- **Background Multithreaded Processing**: Sorting happens asynchronously without freezing or blocking the desktop window.
- **Interactive Preset & Category Manager**: Select built-in presets (`Industrial Safety`, `Office & Business`, `General Media`) or add/delete custom categories directly in the list.
- **Live Treeview Results Table**: Real-time display of classified categories, calibrated confidence percentages, actions taken, and target folder paths.
- **Native File Dialogs & Explorer Integration**: One-click folder picker and Explorer reveal buttons.

---

## 🌐 Alternative: Web-based UI (`app.py`)

### Option A: Double-Click the Launcher
Simply double-click [`run_ui.bat`](file:///c:/Users/Kiruthik%20Kumar/Project/Figma/image_sorter/run_ui.bat). It will launch the server and open your default browser directly at `http://localhost:5050`.

### Option B: Terminal Command
```bash
cd "image_sorter"
python app.py
```
Then open your browser to **`http://localhost:5050`**.

---

## 🚀 Terminal / CLI Usage

From the `image_sorter` folder:

```bash
cd "image_sorter"

# 1. Test API connection
python sorter.py --test-connection

# 2. Dry-run preview
python sorter.py --dry-run

# 3. Sort images:
python sorter.py
```

Sorted images will automatically appear in `sorted_output/<category_name>/`.

---

## 🛠️ Usage & Options

### 1. Test Connection
```bash
python sorter.py --test-connection
```

### 2. Using Built-in Taxonomy Presets
Three presets are provided out-of-the-box:

- **`industrial_safety`** (Default): Pressure Vessels & Heavy Equipment, Piping & Valves, Safety & PPE, Quality Inspection & NDT, Technical Drawings, Other.
- **`office`**: Invoices & Receipts, Contracts & Legal, IDs & Forms, Presentation Slides, Whiteboard Notes, Other.
- **`general`**: Screenshots, Documents, Diagrams, People, Nature, Animals, Products, Artwork, Other.

```bash
python sorter.py --preset industrial_safety
python sorter.py --preset office
```

### 3. Custom Categories
Provide your own comma-separated categories:
```bash
python sorter.py --categories "equipment, piping, ppe, defects, other"
```

### 4. Custom Input/Output Directories & Move Mode
By default, images are **copied** for safety. To **move** them instead:
```bash
python sorter.py --input "C:/Users/username/Pictures" --output "C:/Users/username/SortedPictures" --mode move
```
