"""DynamoDB adapter for data operations."""

import boto3
from datetime import datetime
from typing import Dict, Any, Optional
from decimal import Decimal


class DynamoDBAdapter:
    """Adapter for DynamoDB operations."""
    
    def __init__(self, region_name: str = 'ap-south-1'):
        """Initialize DynamoDB adapter.
        
        Args:
            region_name: AWS region name
        """
        self.dynamodb = boto3.resource('dynamodb', region_name=region_name)
    
    def query_item_with_sk_prefix(
        self,
        table_name: str,
        partition_key_value: str,
        sort_key_prefix: str
    ) -> Optional[Dict[str, Any]]:
        """Query DynamoDB item with sort key prefix.
        
        Args:
            table_name: DynamoDB table name
            partition_key_value: Partition key value
            sort_key_prefix: Sort key prefix to match
        
        Returns:
            First matching item or None
        """
        table = self.dynamodb.Table(table_name)
        response = table.query(
            KeyConditionExpression=boto3.dynamodb.conditions.Key('PK').eq(partition_key_value) &
                                   boto3.dynamodb.conditions.Key('SK').begins_with(sort_key_prefix)
        )
        
        items = response.get('Items')
        if items:
            return items[0]
        return None
    
    def query_item_for_ref_with_sk_prefix(
        self,
        table_name: str,
        partition_key_value: str,
        sort_key_prefix: str
    ) -> Optional[Dict[str, Any]]:
        """Query DynamoDB item with exact sort key match.
        
        Args:
            table_name: DynamoDB table name
            partition_key_value: Partition key value
            sort_key_prefix: Exact sort key value
        
        Returns:
            Matching item or None
        """
        table = self.dynamodb.Table(table_name)
        response = table.query(
            KeyConditionExpression=boto3.dynamodb.conditions.Key('PK').eq(partition_key_value) &
                                   boto3.dynamodb.conditions.Key('SK').eq(sort_key_prefix)
        )
        items = response.get('Items')
        if items:
            return items[0]
        return None
    
    def query_item_with_index_sk_prefix(
        self,
        table_name: str,
        index_name: str,
        partition_key_value: str,
        sort_key_prefix: str
    ) -> Optional[Dict[str, Any]]:
        """Query DynamoDB item using GSI.
        
        Args:
            table_name: DynamoDB table name
            index_name: GSI name
            partition_key_value: GSI partition key value
            sort_key_prefix: GSI sort key value
        
        Returns:
            First matching item or None
        """
        table = self.dynamodb.Table(table_name)
        response = table.query(
            IndexName=index_name,
            KeyConditionExpression=boto3.dynamodb.conditions.Key('GSI1PK').eq(partition_key_value) &
                                   boto3.dynamodb.conditions.Key('GSI1SK').eq(sort_key_prefix)
        )
        items = response.get('Items')
        if items:
            return items[0]
        return None
    
    def update_cv_extract(
        self,
        table_name: str,
        partition_key_value: str,
        sort_key_prefix: str,
        message: str,
        error_code: int,
        overall_matching_score: Decimal
    ) -> Dict[str, Any]:
        """Update CV extract with error info and score.
        
        Args:
            table_name: DynamoDB table name
            partition_key_value: Partition key value
            sort_key_prefix: Sort key value
            message: Error message
            error_code: Error code
            overall_matching_score: Matching score
        
        Returns:
            Update response
        """
        table = self.dynamodb.Table(table_name)
        scoreDetails = "none"
        response = table.update_item(
            Key={
                'PK': partition_key_value,
                'SK': sort_key_prefix
            },
            UpdateExpression="set jdMatchErrorDesc=:m, jdMatchErrorCode=:c, scoreDetails=:scoreDetails, matchingScore=:s",
            ExpressionAttributeValues={
                ':scoreDetails': scoreDetails,
                ':m': message,
                ':c': error_code,
                ':s': overall_matching_score
            },
            ReturnValues="UPDATED_NEW"
        )
        return response
    
    def update_ref_response(
        self,
        table_name: str,
        partition_key: str,
        sort_key: str,
        score_details: str,
        score_details_for_applicant: str,
        matching_score: Decimal,
        email_feedback: str,
        rejection_feedback: str,
        rejection_feedback_for_applicant: str,
        check_exp_data: Any = False,
        reject_on_ctc_or_exp: bool = False
    ) -> Dict[str, Any]:
        """Update referral response with scoring details.
        
        Args:
            table_name: DynamoDB table name
            partition_key: Partition key value
            sort_key: Sort key value
            score_details: Detailed score for recruiter
            score_details_for_applicant: Detailed score for applicant
            matching_score: Overall matching score
            email_feedback: Email summary feedback
            rejection_feedback: Rejection feedback for recruiter
            rejection_feedback_for_applicant: Rejection feedback for applicant
            check_exp_data: CTC/experience check data
            reject_on_ctc_or_exp: Whether rejected on CTC/experience
        
        Returns:
            Update response
        """
        table = self.dynamodb.Table(table_name)
        current_datetime = datetime.now().isoformat()
        jd_match_error_code = 200
        jd_match_error_desc = "Score is generated successfully"
        
        if not reject_on_ctc_or_exp and not check_exp_data:
            update_expr = (
                "SET jdMatchErrorDesc=:jdMatchErrorDesc, "
                "scoreDetails=:scoreDetails, "
                "scoreDetailsForApplicant=:scoreDetailsForApplicant, "
                "matchingScore=:matchingScore, "
                "jdMatchErrorCode=:jdMatchErrorCode, "
                "scoreFetchedDate=:scoreFetchedDate, "
                "emailFeedback=:emailFeedback, "
                "rejectionFeedbackBySystem=:rejectionFeedbackBySystem, "
                "rejectionFeedbackBySystemForApplicant=:rejectionFeedbackBySystemForApplicant"
            )
            expr_values = {
                ":jdMatchErrorDesc": jd_match_error_desc,
                ":scoreDetails": score_details,
                ":scoreDetailsForApplicant": score_details_for_applicant,
                ":matchingScore": matching_score,
                ":jdMatchErrorCode": jd_match_error_code,
                ":scoreFetchedDate": current_datetime,
                ":emailFeedback": email_feedback,
                ":rejectionFeedbackBySystem": rejection_feedback,
                ":rejectionFeedbackBySystemForApplicant": rejection_feedback_for_applicant,
            }
            print("finally updating score info in ..table_name :--", table_name, "partition_key:--", partition_key, "sort_key:--", sort_key)
        else:
            update_expr = (
                "SET jdMatchErrorDesc=:jdMatchErrorDesc, "
                "scoreDetails=:scoreDetails, "
                "scoreDetailsForApplicant=:scoreDetailsForApplicant, "
                "matchingScore=:matchingScore, "
                "jdMatchErrorCode=:jdMatchErrorCode, "
                "scoreFetchedDate=:scoreFetchedDate, "
                "emailFeedback=:emailFeedback, "
                "rejectionFeedbackBySystem=:rejectionFeedbackBySystem, "
                "rejectionFeedbackBySystemForApplicant=:rejectionFeedbackBySystemForApplicant, "
                "checkEXPdata=:checkEXPdata, "
                "rejectCTCAndEXP=:rejectCTCAndEXP"
            )
            expr_values = {
                ":jdMatchErrorDesc": jd_match_error_desc,
                ":scoreDetails": score_details,
                ":scoreDetailsForApplicant": score_details_for_applicant,
                ":matchingScore": matching_score,
                ":jdMatchErrorCode": jd_match_error_code,
                ":scoreFetchedDate": current_datetime,
                ":emailFeedback": email_feedback,
                ":rejectionFeedbackBySystem": rejection_feedback,
                ":rejectionFeedbackBySystemForApplicant": rejection_feedback_for_applicant,
                ":checkEXPdata": check_exp_data,
                ":rejectCTCAndEXP": reject_on_ctc_or_exp,
            }
            print("finally updating score info in ..table_name :--", table_name, "partition_key:--", partition_key, "sort_key:--", sort_key)
        
        response = table.update_item(
            Key={"PK": partition_key, "SK": sort_key},
            UpdateExpression=update_expr,
            ExpressionAttributeValues=expr_values,
            ReturnValues="UPDATED_NEW",
        )
        return response
