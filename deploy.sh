#!/bin/bash
set -e

# ============================================================================
# Variable Definition
# ============================================================================
Lmd_Func="aws-inventory-collector"
ECR_Repo="$Lmd_Func"
ECR_Domain="471112573018.dkr.ecr.ap-south-1.amazonaws.com"
Local_Img_Tag="aws-inventory-image"
ECR_Img_Tag="latest"
ECR_Image_URL=$ECR_Domain/$ECR_Repo:$ECR_Img_Tag
AWS_Region="ap-south-1"

# ============================================================================
# Execution
# ============================================================================
clear
echo ""
echo "###################################################################"
echo "[[[  Running: git fetch --all on current working directory: ]]]"
echo "$PWD"
git fetch --all
echo "###################################################################" && sleep 2
echo ""
echo ""

echo "###################################################################"
echo "[[[  Running git checkout on $1  ]]]"
git checkout $1
echo "###################################################################" && sleep 2
echo ""
echo ""

echo "###################################################################"
echo "[[[  Git status O/P: ]]]"
Git_Status=`git status | head -n 5`
echo "$Git_Status"
echo "###################################################################" && sleep 2
echo ""
echo ""

read -p "Do you want to proceed? (yes/no) " User_Input

case $User_Input in
    yes )
        echo "Proceeding with deployment..."
        echo ""

        echo "###################################################################"
        echo "[[[  Logging in to ECR  ]]]"
        aws ecr get-login-password --region $AWS_Region | docker login --username AWS --password-stdin $ECR_Domain
        echo "###################################################################"
        echo ""

        echo "###################################################################"
        echo "[[[  Building Docker image  ]]]"
        docker image build --no-cache -t $Local_Img_Tag .
        echo "###################################################################"
        echo ""

        echo "###################################################################"
        echo "[[[  Tagging and pushing image to ECR  ]]]"
        docker tag $Local_Img_Tag $ECR_Image_URL
        docker push $ECR_Image_URL
        echo "###################################################################"
        echo ""

        echo "###################################################################"
        echo "[[[  Updating Lambda function  ]]]"
        aws lambda update-function-code \
            --region $AWS_Region \
            --function-name $Lmd_Func \
            --image-uri $ECR_Image_URL
        echo ""
        echo ""
        echo "Lambda Function [$Lmd_Func] current state: "
        aws lambda get-function --region $AWS_Region --function-name $Lmd_Func | egrep -e "State" -e "LastModified"
        echo "###################################################################"
        echo ""
        echo ""
        echo "✓ Deploy complete! Tag: $1"
        break
        ;;
    no )
        echo "Exiting..."
        exit
        ;;
    * )
        echo "Invalid input"
        ;;
esac
