import boto3
import os
import json

dynamodb = boto3.resource('dynamodb')
bedrock_runtime = boto3.client('bedrock-agent-runtime')

TABLE_NAME = os.environ.get('INQUIRY_TABLE', 'InquiryTable')
KB_ID = os.environ.get('KB_ID')
MODEL_ARN = os.environ.get('MODEL_ARN')

CATEGORIES = ["質問", "改善要望", "ポジティブな感想", "ネガティブな感想", "その他"]

def lambda_handler(event, context):
    inquiry_id = event.get('id')
    if not inquiry_id:
        return {"statusCode": 400, "body": "Missing inquiry id"}

    # 1. DynamoDBから reviewText を取得
    table = dynamodb.Table(TABLE_NAME)
    try:
        response = table.get_item(Key={'id': inquiry_id})
        item = response.get('Item')
        if not item or 'reviewText' not in item:
            return {"statusCode": 404, "body": "Inquiry not found or missing reviewText"}
        review_text = item['reviewText']
    except Exception as e:
        return {"statusCode": 500, "body": f"Error reading DynamoDB: {str(e)}"}

    # 2. プロンプト作成
    prompt = f"""
以下の問い合わせ内容を、次のカテゴリのいずれかに分類してください：
「質問」「改善要望」「ポジティブな感想」「ネガティブな感想」「その他」

問い合わせ内容：
「{review_text}」

カテゴリ名だけを日本語で1つ出力してください。
"""

    # 3. Bedrock 呼び出し
    try:
        result = bedrock_runtime.retrieve_and_generate(
            input={"text": prompt},
            retrieveAndGenerateConfiguration={
                "type": "KNOWLEDGE_BASE",
                "knowledgeBaseConfiguration": {
                    "knowledgeBaseId": KB_ID,
                    "modelArn": MODEL_ARN
                }
            }
        )

        output_text = result['output']['text'].strip()
        category = next((cat for cat in CATEGORIES if cat in output_text), "その他")

    except Exception as e:
        return {"statusCode": 500, "body": f"Error from Bedrock: {str(e)}"}

    # 4. DynamoDB に保存
    try:
        table.update_item(
            Key={'id': inquiry_id},
            UpdateExpression='SET Category = :c',
            ExpressionAttributeValues={':c': category}
        )
    except Exception as e:
        return {"statusCode": 500, "body": f"Error updating DynamoDB: {str(e)}"}

    return {
        "statusCode": 200,
        "body": json.dumps({
            "id": inquiry_id,
            "category": category
        })
    }
