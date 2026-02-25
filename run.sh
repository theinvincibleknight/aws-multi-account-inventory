#!/bin/bash

echo "========================================"
echo "AWS Complete Inventory Collection"
echo "========================================"
echo ""
echo "Step 1: Discovering AWS services..."
echo "----------------------------------------"
python3 fetch_aws_services.py
echo ""
echo ""
echo "Step 2: Collecting inventory..."
echo "----------------------------------------"
python3 aws_inventory_dynamic.py
echo ""
echo "Press Enter to exit..."
read
