---
description: Setup PyTorch with CUDA 11.8 support
---

# Setup CUDA Support for BERTopic

This workflow installs PyTorch with CUDA 11.8 support for GPU-accelerated embeddings.

## Prerequisites

- NVIDIA GPU with CUDA 11.8+ support
- Windows system

## Steps

### 1. Remove existing PyTorch (if corrupted)

```powershell
Remove-Item -Path ".venv\Lib\site-packages\torch*" -Recurse -Force -ErrorAction SilentlyContinue
```

### 2. Install PyTorch with CUDA 11.8

// turbo
```powershell
uv pip install --force-reinstall torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118
```

### 3. Verify CUDA installation

// turbo
```powershell
.venv\Scripts\python.exe -c "import torch; print('CUDA available:', torch.cuda.is_available()); print('GPU:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'N/A')"
```

## Important Notes

⚠️ **Do not use `uv run python`** - it will reinstall CPU version from lockfile.

Instead, use one of these methods:

### Option 1: Activate virtual environment first
```powershell
.venv\Scripts\Activate.ps1
python your_script.py
```

### Option 2: Use venv python directly
```powershell
.venv\Scripts\python.exe your_script.py
```

### Option 3: Run backend server
```powershell
.venv\Scripts\python.exe backend/server.py
```

## Configuration

After installation, configure BERTopic to use CUDA:

1. Navigate to `http://localhost:5173/settings/bertopic`
2. Select device: **GPU (CUDA)** or **自动选择**
3. Save configuration

The backend will now use GPU for embeddings computation.
