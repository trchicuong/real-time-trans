@echo off
echo ============================================================
echo Installing PyTorch with CUDA support
echo ============================================================
echo.
echo Current PyTorch version will be uninstalled and replaced
echo with CUDA-enabled version.
echo.
pause

echo.
echo Uninstalling CPU-only PyTorch...
pip uninstall torch torchvision torchaudio -y

echo.
echo Installing PyTorch with CUDA 13.0 support...
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu130

echo.
echo ============================================================
echo Installation completed!
echo ============================================================
echo.
echo Please run: python test_gpu.py
echo to verify GPU detection.
echo.
pause

