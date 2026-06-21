# Installation Guide

This guide walks you through running the UAV Explorer on your computer, **starting from a fresh system with nothing installed**. The target audience is students who have never run a Python program before.

If you already have Python 3.10+ installed and can use a terminal, skip to **[Quick Start for Existing Python Users](#quick-start-for-existing-python-users)** at the bottom.

---

## Part 1 — Windows installation (from scratch)

### Step 1: Download the project

1. Click the green **Code** button at the top of the project's GitHub page.
2. Choose **Download ZIP**.
3. Open your **Downloads** folder. You should see a file like `uav_dashboard_limited-main.zip`.
4. **Right-click** the file → **Extract All** → click **Extract**. A folder will be created (e.g. `uav_dashboard_limited-main`).
5. Open that folder. Inside you should see `app.py`, `requirements.txt`, `data/`, `pages/`, and other files. **Remember the location of this folder** — you'll come back to it.

### Step 2: Install Python (if you don't have it)

1. Go to https://www.python.org/downloads/
2. Click the big yellow **Download Python 3.x.x** button (any version 3.10 or newer is fine).
3. Run the installer.
4. **CRITICAL**: on the first installer screen, **check the box that says "Add Python to PATH"** before you click *Install Now*. If you miss this, the rest of the guide won't work and you'll have to reinstall.
5. Wait for it to finish, then click **Close**.

To check that Python is installed:

- Press **Windows key**, type `cmd`, press **Enter**. A black terminal window opens.
- Type `python --version` and press Enter.
- You should see something like `Python 3.12.5`. If you see "command not found" or similar, Python didn't install correctly — repeat step 2 and **make sure the PATH checkbox is ticked**.

### Step 3: Open the project folder in PowerShell

1. In **File Explorer**, navigate to the extracted project folder (the one with `app.py` inside).
2. Click in the **address bar** at the top of the window. The path turns into editable text.
3. Type `powershell` and press **Enter**. A blue PowerShell window opens, and it's already pointed at the project folder. (No need to `cd` anywhere.)

### Step 4: Create a virtual environment (recommended)

A virtual environment keeps the libraries this app needs separate from your system Python, so they don't interfere with anything else.

In the PowerShell window, type each command on its own line and press **Enter** after each:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

After the second command, you should see `(.venv)` appear at the start of the next line. That means the virtual environment is active.

**If the second command fails with a security error** that says something like "running scripts is disabled":

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

Then run the activation line again.

### Step 5: Install the app's dependencies

Still in PowerShell, with `(.venv)` showing:

```powershell
pip install -r requirements.txt
```

This will download and install Streamlit, Plotly, Pandas, and other libraries. It takes 1–3 minutes depending on your internet speed. If you see warnings (yellow text), that's usually fine; only red error messages need attention.

### Step 6: Run the app

```powershell
streamlit run app.py
```

After a few seconds, your default web browser should open automatically to the app. If it doesn't, look at the PowerShell output for a line like:

```
Local URL: http://localhost:8501
```

and copy that into your browser address bar.

### Step 7: Stopping and re-running

- To **stop** the app: in the PowerShell window, press **Ctrl+C**.
- To **start it again later** (without re-installing anything): open PowerShell in the project folder (Step 3), activate the venv, and run streamlit:

```powershell
.\.venv\Scripts\Activate.ps1
streamlit run app.py
```

---

## Part 2 — Linux installation (from scratch)

Tested on Ubuntu 22.04+ / Debian 12+ / Fedora 39+. Other distros are similar but package commands differ.

### Step 1: Download the project

1. Open your web browser, go to the project's GitHub page.
2. Click the green **Code** button → **Download ZIP**.
3. Save the file (typically to `~/Downloads`).
4. Open a **terminal** (Ctrl+Alt+T on most distros).
5. Unzip and enter the folder:

```bash
cd ~/Downloads
unzip uav_dashboard_limited-main.zip
cd uav_dashboard_limited-main
```

(Replace the filename with whatever you actually got — `ls` to see.)

### Step 2: Install Python (if you don't have it)

Most Linux distributions ship with Python already, but you may need `pip` and `venv` modules separately.

**Ubuntu / Debian:**

```bash
sudo apt update
sudo apt install python3 python3-pip python3-venv
```

**Fedora / RHEL:**

```bash
sudo dnf install python3 python3-pip
```

**Arch:**

```bash
sudo pacman -S python python-pip
```

Verify:

```bash
python3 --version
```

You should see `Python 3.10` or newer.

### Step 3: Create a virtual environment

From the project folder (where `app.py` lives):

```bash
python3 -m venv .venv
source .venv/bin/activate
```

After the second command, your prompt should change to show `(.venv)` at the start.

### Step 4: Install dependencies

```bash
pip install -r requirements.txt
```

Wait for it to finish (1–3 minutes).

### Step 5: Run the app

```bash
streamlit run app.py
```

A browser tab should open automatically. If it doesn't, copy the `Local URL` shown in the terminal into your browser.

### Step 6: Stopping and re-running

- **Stop**: press **Ctrl+C** in the terminal.
- **Start again later**: open a terminal in the project folder, then:

```bash
source .venv/bin/activate
streamlit run app.py
```

---

## Troubleshooting

### "Python is not recognized" (Windows)

You forgot to check "Add Python to PATH" during install. Re-run the Python installer, choose **Modify**, click through, and tick the PATH option.

### "pip is not recognized"

This is part of Python 3.10+ but sometimes missing on older Linux installs. Try `sudo apt install python3-pip` (Debian/Ubuntu) or `python -m ensurepip --upgrade`.

### "ModuleNotFoundError: No module named 'streamlit'"

You ran `streamlit run app.py` without activating the virtual environment first. Always activate the venv before running. See Step 4 / Step 3 for each OS.

### App opens but shows errors

- Make sure you're in the right folder (`app.py` should be in the folder where you run the command).
- Make sure `data/uav_clean.csv` exists in the `data/` folder.
- Check the terminal/PowerShell window for the actual error message. Most errors are about missing or corrupted dependencies — try `pip install -r requirements.txt --upgrade` to refresh them.

### Port 8501 already in use

Another Streamlit app is already running on that port. Either stop it (Ctrl+C in its window) or run on a different port:

```bash
streamlit run app.py --server.port 8502
```

### "Permission denied" / antivirus blocking on Windows

Some antivirus tools flag Python venvs as suspicious. Either whitelist the project folder, or temporarily disable real-time scanning while installing. The dependencies are all standard scientific-Python packages (Streamlit, Plotly, Pandas, NumPy, SciPy, scikit-learn) — none of them are malicious.

---

## Quick Start for Existing Python Users

If you already have Python 3.10+, pip, and a terminal:

```bash
git clone <repo-url>
cd uav_dashboard_limited
python -m venv .venv
source .venv/bin/activate   # (.venv\Scripts\Activate.ps1 on Windows)
pip install -r requirements.txt
streamlit run app.py
```

---

## Requirements summary

- **Python**: 3.10 or newer (3.11 or 3.12 recommended)
- **OS**: Windows 10/11, macOS 11+, or any modern Linux
- **RAM**: 2 GB minimum, 4 GB recommended (Streamlit + Plotly are memory-hungry when rendering large scatters)
- **Disk**: ~500 MB for the venv + dependencies, ~5 MB for the app itself
- **Internet**: required for the first `pip install` only; the app runs entirely offline thereafter.

---

For questions about using the app (what each tab does, how to interpret charts), see `USER_GUIDE.md`. For licensing, see `LICENSE-CODE.md` and `LICENSE-DATA.md`.
