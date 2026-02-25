@echo off
echo ========================================
echo AWS Complete Inventory Collection
echo ========================================
echo.
echo Step 1: Discovering AWS services...
echo ----------------------------------------
python fetch_aws_services.py
echo.
echo.
echo Step 2: Collecting inventory...
echo ----------------------------------------
python aws_inventory_dynamic.py
echo.
pause
