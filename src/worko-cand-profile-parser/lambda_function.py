


import json
import boto3
import os
import time
from urllib.parse import unquote_plus
from urllib.parse import unquote_plus
from concurrent.futures import ThreadPoolExecutor, as_completed
# second deployment11
start_time = time.time()
# Initialize Bedrock clients
region = 'ap-south-1'
dynamodb = boto3.resource('dynamodb')
bedrock = boto3.client(service_name='bedrock', region_name = region)
bedrock_runtime = boto3.client(service_name='bedrock-runtime', region_name = region)
sqs = boto3.client('sqs')
from utils import *
# best deployment1

def lambda_handler(event, context):
    # example_path1="s3://worko-corporate-cand-profile-dev/companies/01JWAQF1G96E0SE9XHXSFGHNWW/bulk-cvs/01KD2WDTS7RZKEJ6QFK87MDC0K.pdf"
    # example_path2= "s3://worko-admin-cand-profile-dev/bulk-cvs/01KEH892ZACXJVV996SPKP0948.pdf"
    print("got event:",event)
    try:
        metadata = get_meta_data(event)
        if metadata.get("skipparsing","")=="true":
            print("skipParsing as got info to skip in metadata")
            return {'statusCode': 200, 'body': json.dumps(f'skipParsing as got info to skip in metadata')}
    except Exception as e:
        print("following normal flow")

        
    env = os.environ.get("ENVIRONMENT", "dev")
    GCP_DATABASE_NAME = "worko-corp-db-"+env
    GCP_secret_name = "GCP-firestore-secret-"+env
    DBManager = FirestoreManager(GCP_secret_name,GCP_DATABASE_NAME)
    collection_name_for_firstore_updating_counts = "bulkSourceTypeResumes"
    env=os.environ.get("ENVIRONMENT", "dev")
    
    # Initialize Azure OpenAI models
    azure_openai_secret_name = "AZURE-openai-secret-multimodel-"+env
    azure_openai_secret = get_secret(azure_openai_secret_name)
    gpt4 = AzureOpenAIClient(azure_openai_secret,model="gpt-4o")
    gpt4_1_mini = AzureOpenAIClient(azure_openai_secret,model="gpt-4.1-mini")
    gpt_models = [gpt4,gpt4_1_mini]
    
    # Initialize GPT-5 models
    gpt52_client = AzureOpenAIClient(azure_openai_secret, model="gpt-5.2")
    gpt5_models = [gpt52_client, gpt52_client]
    
    # Use Gemini models
    gcp_credentials = get_secret(GCP_secret_name)
    # gemini_pro_2_5_pro = GeminiClient(gcp_credentials, env, model="gemini-2.5-pro")
    gemini_pro_2_5_flash = GeminiClient(gcp_credentials, env, model="gemini-2.5-flash")
   
    gemini_models = [gemini_pro_2_5_flash, gemini_pro_2_5_flash]
    
    retry_queue_name = "worko-cand-profile-parser-retry-queue-"+env
    key_resume_elements = ["candidateName","candidateEmail"]
    
    try:
        if json.loads(event.get("Records",[])[0].get("body", "{}")).get("eventType", "")=="RetrySQS":
        # if 'Records' in event and event.get('Records', []) and 'eventSource' in event['Records'][0] and json.loads(event['Records'][0].get('body', '{}')).get('Records', [{}])[0].get('eventSource') != 'aws:s3':
            #condition 1 will check sqs event condition will check its a retry or sqs-s3 event if sqs-s3 event the it will say false i=and s3 flow will be run
            print("This Event is triggered by retry SQS...")
            retry_body = json.loads(event["Records"][0]["body"])
            retry_counter = retry_body.get("retry_counter", 1)
            print(f"retry_counter for this batch : {retry_counter}")
            if retry_counter >= 5:
                print(f"Message received {retry_counter} times, sending to DLQ")
                dlq_name = f"worko-cand-profile-parser-dlq-{env}"
                dlq_url = get_queue_url(dlq_name)
                retry_body["bulksourcetyperesumeid"] =bulksourcetyperesumeid
                sqs.send_message(QueueUrl=dlq_url, MessageBody=json.dumps(retry_body))

                cand_data = {"status": "FAILED"}  # send staus failed in ase of max retry>3
                processingStatus = "FAILED"
                updated_firstore_resume_status(processingStatus,bulksourcetyperesumeid,cand_data,DBManager) 

                return {'statusCode': 200, 'body': json.dumps('Moved to DLQ')}
            else:
                records = retry_body["records"]
                print(f"Processing {len(records)} records from retry SQS with retry_counter {retry_counter}")
                try:
                    for record_number, record in enumerate(records):
                        # Parse the S3 event from the record body
                        s3_event_str = record.get("body", "{}")
                        s3_event = json.loads(s3_event_str)
                        
                        # Extract bucket and key from S3 event
                        s3_bucket_name = s3_event["Records"][0]["s3"]["bucket"]["name"]
                        object_key = unquote_plus(s3_event["Records"][0]["s3"]["object"]["key"])
                        
                        metadata = get_meta_data(s3_bucket_name, object_key)
                        print("meta data for sqs-s3 triger", metadata)
                        company_id = metadata.get("company_id", "")
                        bulksourcetyperesumeid = metadata.get("bulksourcetyperesumeid","")

                        
                        if not bulksourcetyperesumeid:
                            print(f"Missing bulksourcetyperesumeid in SQS message. Skipping processing.")
                            return {'statusCode': 400, 'body': json.dumps('Missing bulksourcetyperesumeid')}
                        
                        doc = get_counts(collection_name_for_firstore_updating_counts,bulksourcetyperesumeid,DBManager)
                        
                        # processed_text = body.get("processed_text","")
                        processed_text = get_text_from_cv(s3_bucket_name,object_key)
                        
                        file_name = object_key.split("/")[-1]
                        

                        
                        if processed_text:
                            retry_counter+=1
                            try:
                                correct_parsing_try = 3
                                for i in range(correct_parsing_try):
                                    cvExtractedParsed = process_cv(processed_text,gpt_models,gpt5_models,gemini_models)
                                    if has_key_elements(cvExtractedParsed, key_resume_elements, 2):
                                        break
                                    else:
                                        print(f"cvExtractedParsed is't valid doing one more time : {cvExtractedParsed}")
                                        continue


                                
                            except Exception as execution_error :
                                if any(term in str(execution_error) for term in ['throttling', 'throttled', 'rate limit', 'too many requests', '429']) :
                            
                                    print(f"Error of {execution_error} now sending sqs for starting again in next 90 seconds")
                                    delay_seconds = 90*retry_counter
                                    send_sqs_for_throttling_error(retry_queue_name, record, retry_counter, delay_seconds)
                                    break
                            if cvExtractedParsed=="Failed":
                                status = "FAILED"

                                print(f"this is a failed resume, so trigring sqs for this resume and updating as Failed in firestore")
                                sqs_send_data = {"companyId": company_id,
                                        "candidateCvAwsS3FileName":file_name,
                                        "cvExtractedParsed":cvExtractedParsed}
                                send_final_sqs_for_cvExtractparsed(sqs_send_data)
                                cand_data = {"status": status}
                                updated_firstore_resume_status(status,bulksourcetyperesumeid,cand_data,DBManager)   

                            if cvExtractedParsed:
                                # send_final_cv_sqs(cvExtractedParsed,file_name,object_key,DBManager)
                                dublicat_data = check_firstore_dubliacy(cvExtractedParsed, object_key, DBManager)

                                
                                if dublicat_data is None:
                                    print(f"this is a unique resume, so trigring sqs for this resume and updating as SUCCESS in firestore")
                                    sqs_send_data = {"companyId": company_id,
                                            "candidateCvAwsS3FileName":file_name,
                                            "cvExtractedParsed":cvExtractedParsed}
                                    send_final_sqs_for_cvExtractparsed(sqs_send_data)
                                    status = "SUCCESS"
                                    cand_data = get_data_to_update_in_firstore(cvExtractedParsed,status)
                                    updated_firstore_resume_status(status,bulksourcetyperesumeid,cand_data,DBManager)   

                                elif dublicat_data is not None:
                                    print(f"Found dublicate record in firstore, Not trigring sqs for this resume and updating status as DUPLICATE in firestore:- {dublicat_data}")
                                    status = "DUPLICATE"
                                    cand_data = get_data_to_update_in_firstore(cvExtractedParsed,status)
                                    updated_firstore_resume_status(status,bulksourcetyperesumeid,cand_data,DBManager)   
                                    # if company_id:
                                    #     sqs_send_data = {"event": "CORPORATE_CAND_PROFILE_BULK_UPLOAD",
                                    #         "companyId": company_id,
                                    #         "candidateCvAwsS3FileName":file_name,
                                    #         "cvExtractedParsed":cvExtractedParsed}
                                        

                                    # else:
                                    #     sqs_send_data = {
                                    #         "candidateCvAwsS3FileName":file_name,
                                    #         "event":"ADMIN_CAND_PROFILE_BULK_UPLOAD",
                                    #         "cvExtractedParsed":cvExtractedParsed
                                    #     }
                                else:
                                    print(f"Error in checking dublicacy in firstore for this resume with email {cvExtractedParsed.get('candidateEmail','')} and phone number {cvExtractedParsed.get('candidatePhoneNumber','')}")    

                        else:
                            print(f"Missing processed_text in SQS message body. Marking as FAILED.")
                            cand_data = {"status": "FAILED"}
                            processingStatus = "FAILED"
                            updated_firstore_resume_status(processingStatus,bulksourcetyperesumeid,cand_data,DBManager)
                except Exception as e :
                    print(f"errore with sqs retry event :- {e}")
        else:
            print("This Event is triggered by S3...")
            print(f"Got batch of {len(event['Records'])} cvs for processing in parallel")
            
            # Extract bulksourcetyperesumeid from first record for email summary
            first_record = event['Records'][0]
            first_s3_event = json.loads(first_record['body'])["Records"][0]["s3"]
            first_bucket = first_s3_event['bucket']['name']
            first_key = unquote_plus(first_s3_event['object']['key'])
            first_metadata = get_meta_data(first_bucket, first_key)
            bulksourcetyperesumeid = first_metadata.get("bulksourcetyperesumeid", "")
            metadata = first_metadata

            
            def process_single_cv(record):
                """Process a single CV record"""
                try:
                    s3_event = json.loads(record['body'])["Records"][0]["s3"]
                    bucket_name = s3_event['bucket']['name']
                    object_key = unquote_plus(s3_event['object']['key'])
                    metadata = get_meta_data(bucket_name, object_key)
                    file_name = object_key.split("/")[-1]
                    
                    print(f"Processing file: {file_name}")
                    processed_text = get_text_from_cv(bucket_name, object_key)
                    
                    bulksourcetyperesumeid = metadata.get("bulksourcetyperesumeid", "")
                    doc = get_counts(collection_name_for_firstore_updating_counts, bulksourcetyperesumeid, DBManager)

                    if "companies" in object_key:
                        company_id = object_key.split("/")[1]
                        metadata["company_id"] = company_id
                    else:
                        company_id = ""
                    
                    if not processed_text:
                        print(f"Failed to extract text from S3 for {file_name}, sending to retry queue")
                        send_sqs_for_throttling_error(retry_queue_name, record, 1, 30)
                        return {'status': 'retry', 'file': file_name}
                
                    try:
                        correct_parsing_try = 3
                        for i in range(correct_parsing_try):
                            cvExtractedParsed = process_cv(processed_text,gpt_models,gpt5_models,gemini_models)
                            if has_key_elements(cvExtractedParsed, key_resume_elements, 2):
                                break
                            else:
                                print(f"cvExtractedParsed is't valid doing one more time : {cvExtractedParsed}")
                                continue
                        # cvExtractedParsed = process_cv(processed_text, gpt_models, gpt5_models, gemini_models)

                    except Exception as execution_error:
                        if any(term in str(execution_error).lower() for term in ['throttling', 'throttled', 'rate limit', 'too many requests', '429', 'quota', 'resource exhausted']):
                            print(f"Throttling error for {file_name}: {execution_error}, sending to retry queue")
                            send_sqs_for_throttling_error(retry_queue_name, record, 1, 90)
                            return {'status': 'throttled', 'file': file_name}
                        else:
                            print(f"ERROR: Non-throttling exception in process_cv() for {file_name}: {execution_error}")
                            print(f"ERROR: CV {file_name} failed during process_cv() - marking as FAILED and updating Firestore")
                            cand_data = {"status": "FAILED"}
                            updated_firstore_resume_status("FAILED", bulksourcetyperesumeid, cand_data, DBManager)
                            return {'status': 'error', 'file': file_name}
                
                    if cvExtractedParsed == "Failed":
                        status = "FAILED"
                        print(f"Failed resume {file_name}, triggering sqs and updating as Failed in firestore")
                        sqs_send_data = {"companyId": company_id,
                                "candidateCvAwsS3FileName": file_name,
                                "cvExtractedParsed": cvExtractedParsed}
                        send_final_sqs_for_cvExtractparsed(sqs_send_data)
                        cand_data = {"status": status}
                        updated_firstore_resume_status(status, bulksourcetyperesumeid, cand_data, DBManager)
                        return {'status': 'failed', 'file': file_name}

                    elif cvExtractedParsed:
                        print(f"Successfully parsed {file_name}")
                        try:
                            dublicat_data = check_firstore_dubliacy(cvExtractedParsed, object_key, DBManager)
                            if dublicat_data is not None:
                                print(f"Found duplicate record for {file_name}, updating status as DUPLICATE")
                                status = "DUPLICATE"
                                cand_data = get_data_to_update_in_firstore(cvExtractedParsed, status)
                                updated_firstore_resume_status(status, bulksourcetyperesumeid, cand_data, DBManager)
                                return {'status': 'duplicate', 'file': file_name}
                            else:
                                sqs_send_data = {"companyId": company_id,
                                            "candidateCvAwsS3FileName": file_name,
                                            "cvExtractedParsed": cvExtractedParsed}
                                send_final_sqs_for_cvExtractparsed(sqs_send_data)
                                status = "SUCCESS"
                                cand_data = get_data_to_update_in_firstore(cvExtractedParsed, status)
                                updated_firstore_resume_status(status, bulksourcetyperesumeid, cand_data, DBManager)
                                return {'status': 'success', 'file': file_name}
                        except Exception as e:
                            print(f"ERROR: Exception in process_parsed_cv_json() or Firestore operations for {file_name}: {e}")
                            print(f"ERROR: CV {file_name} failed during post-processing - marking as FAILED and updating Firestore")
                            cand_data = {"status": "FAILED"}
                            updated_firstore_resume_status("FAILED", bulksourcetyperesumeid, cand_data, DBManager)
                            return {'status': 'error', 'file': file_name}
                    else:
                        print(f"ERROR: process_cv() returned None for {file_name} - marking as FAILED and updating Firestore")
                        cand_data = {"status": "FAILED"}
                        updated_firstore_resume_status("FAILED", bulksourcetyperesumeid, cand_data, DBManager)
                        return {'status': 'no_data', 'file': file_name}
                        
                except Exception as e:
                    print(f"Unexpected error processing record: {e}")
                    return {'status': 'error', 'file': 'unknown', 'error': str(e)}
            
            # Process all CVs in parallel
            with ThreadPoolExecutor(max_workers=10) as executor:
                futures = {executor.submit(process_single_cv, record): record for record in event['Records']}
                results = []
                for future in as_completed(futures):
                    try:
                        result = future.result()
                        results.append(result)
                        print(f"Completed processing: {result}")
                    except Exception as e:
                        print(f"Error in parallel processing: {e}")
                        results.append({'status': 'error', 'error': str(e)})
            
            print(f"Parallel processing completed. Results: {results}")
                
                

        this_is_last_resume = if_last_cv(collection_name_for_firstore_updating_counts,bulksourcetyperesumeid,DBManager)
        # this_is_last_resume=True  #$$$
        # this_is_last_resume =True   #$$ test

        if this_is_last_resume:
            
            large_files = DBManager.get_documents_by_bulkSourceTypeResumeId_and_status("bulkSourceTypeParseResumes", bulksourcetyperesumeid,"LARGE_RESUME_FILE")
            print("large_files_list1 ",large_files)
            try:
                large_files_list = [i["userResumeFileName"] for i in large_files]
                print("large_files_list2",large_files_list)
            except Exception as e:
                print("Got error while getting large files data",e)


            Data_of_cv  = DBManager.get_documents_by_bulkSourceTypeResumeId("bulkSourceTypeParseResumes",bulksourcetyperesumeid)
            print("all parsed cv data in bulk collection",str(Data_of_cv)[:100],"...")
            all_cv_parsing_summary =build_status_summary(Data_of_cv,large_files_list)
            send_cv_summary_email(all_cv_parsing_summary, metadata)


    except Exception as e:
        print(f"Error in lambda_handler: {e}")
        cand_data = {"status": "FAILED"}  # send staus failed in ase of max retry>3
        processingStatus = "FAILED"
        updated_firstore_resume_status(processingStatus,bulksourcetyperesumeid,cand_data,DBManager) 
        return {'statusCode': 500, 'body': json.dumps(f'Error: {e}')}


# if __name__ == "__main__":
    # event ={'Records': [{'eventVersion': '2.1', 'eventSource': 'aws:s3', 'awsRegion': 'ap-south-1', 'eventTime': '2026-02-13T10:54:41.817Z', 'eventName': 'ObjectCreated:Put', 'userIdentity': {'principalId': 'AWS:AROATCKANHWV2MBXXE3V6:worko-corp-dev-workoCorp'}, 'requestParameters': {'sourceIPAddress': '103.176.210.127'}, 'responseElements': {'x-amz-request-id': 'A1ZX01WYQJ2Y5JH6', 'x-amz-id-2': 'wnmtopZYMlwdUUFEXUaSsPUXlfUOrsb3JKWieIvgG+zU+Hph9o1vtOaooaRN2iInFw8mWnp2dHqT/iRGvosQet9Nbvr5t1qpjWBXU656KVw='}, 's3': {'s3SchemaVersion': '1.0', 'configurationId': 'a6c870b0-fd5d-4747-ac88-27e26b7ecba5', 'bucket': {'name': 'worko-admin-cand-profile-dev', 'ownerIdentity': {'principalId': 'A1V0APDMR493SG'}, 'arn': 'arn:aws:s3:::worko-admin-cand-profile-dev'}, 'object': {'key': 'bulk-cvs/01KHBA6ZW2MDQWJN4WE2YJXFDV.pdf', 'size': 58816, 'eTag': 'ecdcfaabc0c96728a65b559256cc68f6', 'sequencer': '00698F02F1C38704BF'}}}]}  
    # event = {"Records":[{"eventVersion":"2.1","eventSource":"aws:s3","awsRegion":"ap-south-1","eventTime":"2026-02-13T05:21:25.288Z","eventName":"ObjectCreated:Put","userIdentity":{"principalId":"AWS:AROATCKANHWV2MBXXE3V6:worko-corp-dev-workoCorp"},"requestParameters":{"sourceIPAddress":"103.176.210.127"},"responseElements":{"x-amz-request-id":"A7DP139505J83HYT","x-amz-id-2":"7qLalj01knes4BpKEg5sLH1PjcL91s9OGs69//2J775bV3sZLPXHSwrmOd1NLv3T0+tMFZQL58bR0lLKCVHtJFEc5LKEe1zZmU5N5y6A+Q4="},"s3":{"s3SchemaVersion":"1.0","configurationId":"a6c870b0-fd5d-4747-ac88-27e26b7ecba5","bucket":{"name":"worko-admin-cand-profile-dev","ownerIdentity":{"principalId":"A1V0APDMR493SG"},"arn":"arn:aws:s3:::worko-admin-cand-profile-dev"},"object":{"key":"bulk-cvs/01KHAQ4QXFP0HW6BSFRK926JH1.pdf","size":225212,"eTag":"296eeb83abfe1d84d866db9a55621a78","sequencer":"00698EB4D53FB3565C"}}}]}
    # event= {'Records': 
    #         [{'messageId': '200dbd50-972f-4e1f-b649-e08fe263ea26', 'receiptHandle': 'AQEBx+TZ+WFSQcByKvLWnm0JsiPozA1SR65NOIzdGwoCbxABRC0mrB2Uvfy7KHkxaYF0f+USJtXnAv8aZx11XFWdUzXtbv/9820o1PP527vRnQ83pIHwzaKDwNnlJ6Ys1+NKwsgY7XTA4WYXg+uhNMEhCd4V9zWMvQSKGvObghkzaMiHbUDaRAQz614VhthKjHoNvccaKnhhd5a14K1L1q2u/7vs+/9cVF9yam0Boft5Z22dRl3ITbv8A0SAZMJcznSRerL0g4xl4ri/ZYTtrwKVlUwWo8+rSbXvf/wixo8pw339oD9g61YrE3oERfhees9OSstfaDM5UGg+EdOpHvdsxPrVLv+GcHiWPOJzOAN8QoqajpnRuRmG7gtoxvC7fAXCxhPby0Ld2Esiko+MLMV1iR7SEAAo1DklnoPsEHxZ2Z5fVvzZMz2JTqDt2XdQ1IvT', 
    #           'body': '{"bucket_name":"worko-admin-cand-profile-dev","processed_text": "Shatakshi Mishra LinkedIn | +91 6386311282 | mishrashatakshi009@gmail.com WORK EXPERIENCE Zulu Club (0\\u21921 Hyperlocal Fashion & Lifestyle Startup) Gurugram Founding Member & Chief of Staff May 2025- Present Strategy & Growth \\u2022 Acted as Chief of Staff to Founder & CEO, managing strategic initiatives and freeing 15\\u201320% CEO bandwidth for fundraising and external partnerships. \\u2022 Supported pre-seed fundraising, preparing investor materials and analyses that helped secure \\u20b92 crore from early investors \\u2022 Built multi-functional operations from scratch, handling 5+ verticals (partnerships, category management, inventory, marketing, tech, fund-raise, hiring, etc) 0\\u21921 Business Building & GTM \\u2022 Launched \\u201cTry at Home\\u201d model from 0\\u21921 \\u2014 curated assortments across Men\\u2019s, Women\\u2019s, Home D\\u00e9cor, and Beauty (2000+ SKUs), set up dark store operations, and operationalised GTM strategies \\u2022 Built outlet partnerships function from 0\\u21921 \\u2014 identified, pitched, and onboarded 100+ outlets across fashion, lifestyle, and accessories, creating the marketplace\\u2019s initial partner network and contributing 85% of early GMV \\u2022 Piloted AI-based cataloguing (image isolation, upscaling), reducing manual listing effort by 30% and cutting onboarding turnaround from 4 days \\u2192 2 days Marketing & Customer Acquisition \\u2022 Orchestrated gamified Instagram ad campaigns, increasing engagement 2.3x and improving CTR from 0.1% \\u2192 3%, driving 1000+ incremental sign- ups \\u2022 Ran Instagram performance marketing campaigns with \\u20b91 lakh budget, lowering CAC by 75% and scaling reach to 10,000+ users in 2 months \\u2022 Coordinated 30+ content shoots, delivering outlet storytelling campaigns that improved brand discovery and boosted engagement by 30% \\u2022 Planned and executed 45+ BTL activations (pop-ups, offline events), generating 90% uplift in downloads and 25% increase in sales Product \\u2022 Zulu Club App- Collaborated with product & tech teams to execute multiple versions of Zulu Club app, delivering improved content curation and aesthetics, which led to 28% higher session times and 7.5% increase in order conversion rates \\u2022 Zulu Club Website- Conceptualised and executed end-to-end website redesign \\u2014 from user research and content curation to UI/UX design and rollout \\u2014 improving discoverability, boosting average session times, raising lead-to-order conversion \\u2022 Developed Outlet/Seller page product flow on web platform, aligning catalogue design with buyer journeys Samagra Transforming Governance New Delhi Management Consultant, Strategy & Ops for President of India Nov 2023 \\u2013 Oct 2024 Project & Stakeholder Management \\u2022 Identified, conceptualized & led complex projects, played advocate to the President of India; Secretaries, Addl Secretaries and Directors of various Govt Ministries, PSUs \\u2022 Developed a strategic roadmap for administrative reforms for President of India\\u2019s Secretariat, streamlining recruitment, services, transitions, impacting 500+ personnel \\u2022 Reimagined the role of the President of India in Viksit Bharat, crafting a strategic framework for events at Rashtrapati Bhavan, Presidential tours- international and domestic, driving 33% increased public engagement through enhanced outreach \\u2022 Spearheaded the end-to-end planning and management of the 2024 Swearing-in Ceremony for the Union Council of Ministers, Bhartiya Kala Mahotsav, ensuring flawless execution for an audience of 8k+ and 1 lakh+ respectively \\u2022 Designed a blitzkrieg outreach strategy with partners like EaseMyTrip, Tripadvisor, Paytm Insider, increasing footfall at Rashtrapati Bhavan attractions by 45% YoY \\u2022 Contributed to the creation of Goods & Services Procurement Playbook, improving vendor onboarding, reducing turnaround time for critical tenders by 30% \\u2022 Collaborated with the GoI ministries to drive the decolonization and Indianization of 150+ artifacts across Presidential estates, modernizing the historical narrative\\\\ \\u2022 Continuously engaged in creating timelines, milestones, project plans, manage project teams, track success through measurable KPIs & delivering executive reports/ presentations to Govt stakeholders and C-Suite of collaborating private companies Customer Experience and Digital Engagement \\u2022 Led the overhaul of 6 Rashtrapati Bhavan websites optimizing customer journey by conducting user research, A/B Testing, revamp of SEO strategy, intuitiveness and accessibility features of UI/UX, leveraging Google Analytics, Microsoft Clarity, Figma, etc, Boosted Y-O-Y website visitor numbers by 50% and funnel optimization of bookings from 8% to 16% conversion, reducing bounce rate by 20% \\u2022 Optimized digital touchpoints by launching the Rashtrapati Bhavan app through pan-India rollout to all Android and iOS users \\u2022 Data Driven Improvements: Implemented target-based performance management, fostering ownership among junior officers, reviving 20+ languishing projects \\u2022 Process Automation: Strategized and implemented 10+ E-Governance initiatives, optimized process turnaround, reducing bottlenecks between departments by 25% \\u2022 Created strategy for improving product and CX at Rashtrapati Bhavan Main Building, Museum, Amrit Udyan, Rashtrapati Estates-Shimla & Hyderabad Increasing NPS score by 18%, reducing complaints by 24% and increasing self-service adoption rates by 15% Achievements \\u2022 Received Spot Award of Excellence for outstanding project management in finalizing the upcoming Tribal Museum\'s content and curation Ministry of Skill Development & Entrepreneurship New Delhi Consultant, Strategy & Ops for SANKALP Scheme Oct 2021 Oct 2023 \\u2022 Spearheaded the formation and enhancement of District Skill Committees in coordination with district administrations, aligning efforts with line departments to strengthen skill development across the region, leading to a 30% increase in skill training participation \\u2022 Pioneered first-ever Skill Gap Analysis and made District Skill Development Plan \\u201922 for East Delhi, focusing on local demand and supply of skills \\u2022 Mapped tourist potential areas in the district and made plan for drawing more tourists with Tourism & Hospitality Sector Skill Council \\u2022 Facilitated apprenticeship promotion through NAPS, organizing PMNAM at ITIs around Delhi providing apprenticeship offers to 700+ candidates \\u2022 Strengthened National Education Policy (NEP) 2020 through demand aggregation of job roles and institutional mapping in the district, formulated and launched Adult Education Project for educating 140 people of slum areas in the district, in tandem with NIOS \\u2022 Conceptualized and executed marketing strategies for Self-Help Group (SHG) products, leading to the successful Mahila Hunar Haat at Akshardham Metro Station \\u2022 Negotiated and onboarded key CSR partnerships with organizations like Xiaomi, TATA Motors, IBM, and NGOs like Mahindra Pride, Quest Alliance resulting in 22,000+ candidates skilled in a year, driving economic upliftment \\u2022 Orchestrated disaster response efforts during the Delhi Floods 2023, managing the evacuation of 1,500+ individuals and ensuring effective crisis management in flood-prone areas \\u2022 Designed and deployed Project Rahnuma, providing 2500+ individuals with personalized counselling and skilling support to enhance livelihood opportunities. \\u2022 Conceptualised and implemented Project Mohini: Skill Development and 100% Placement of 60+ transgender persons Achievements \\u2022 Handpicked (9/650) by. Secretary, MSDE for developing a Model District Skill Development Plan for the country, by leading a team of 9 to draft the plan based on insights from RDSDE and SANKALP teams \\u2022 Selected (7/650) to be part of Core Team to organise Akhil Bhartiya Shiksha Samagam \\u201823 having a footfall of 1 lakh+ people Certificate of Recognition from CEO, National Skill Development Corporation for contribution in making the event a success LegalXGen Bengaluru Senior Analyst, CEO\\u2019s Office Sep 2017 Dec 2019 \\u2022 Reduced time-to-market of releases by a month through targeted process enhancements, elevating operational efficiency and productivity \\u2022 Elevated SLAs by actively engaging with leadership, configuring new feature requirements and ensuring precise sprint scope \\u2022 Cut revenue leakage by 30% through implementation of billing automation and unpaid invoices reminder features \\u2022 Collaborated with presales, sales and marketing teams in solutioning, drafting sales and marketing pitch to triple the client base Ericsson Noida Engineer, Operations-Service Requirement Fulfillment Jul 2016 Aug 2017 \\u2022 Sprint, USA | Trunk Management Testing: Handled execution of T1 Provisioning, Testing, Install & Disconnect of Normal and 911 calls \\u2022 Digicel, PNG | Back Office: Overhauled the network mapping directory, reducing troubleshooting time by 30% in critical network failures, impacting 2.5mn users LEADERSHIP \\u2022 Chief of Staff to Founder & CEO of Zulu Club, managed 20+ people of 3 verticals- Business, Tech/Product and Marketing \\u2022 Identified, conceptualized & led complex projects, played advocate to the President of India; Secretaries, Addl Secretaries and Directors of various Govt Ministries & PSUs \\u2022 Continuously engaged in creating timelines, milestones, project plans, manage project teams, track success through measurable KPIs & delivering executive reports/presentations to Govt stakeholders and C-Suite of collaborating private companies EDUCATION Indian Institute of Management, Kozhikode 2021-2023 Public Policy & Management Indira Gandhi Delhi Technical University 2012-2016 B.Tech, Information Technology", '
    #           '"object_key": "bulk-cvs/01KHBG74CP2BRYG94V236S8WT0.pdf", '
    #           '"from": "throttling error", "retry_counter": 1, '
    #           '"metadata": {"bulksourcetyperesumeid": "01KHBG70MXK0BEWBQ5AMGW3TCX", '
    #           '"workoadminuseremail": "raj.ghosh@worko.ai"}}',
    #            'attributes': {'ApproximateReceiveCount': '1', 'AWSTraceHeader': 'Root=1-698f1b8b-04a0bf1f422269094319ee89;Parent=48e3c2fe9aae6204;Sampled=0;Lineage=1:3a1bb061:0', 'SentTimestamp': '1770986390226',
    #                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        'SenderId': 'AROATCKANHWVU3UAPBTQ2:worko-cand-profile-parser-dev', 'ApproximateFirstReceiveTimestamp': '1770986455912'}, 
    #           'messageAttributes': {}, 'md5OfBody': '30f2f4eb84e8973f7ee78c6be6db1c2b', 'eventSource': 'aws:sqs', 'eventSourceARN': 'arn:aws:sqs:ap-south-1:211125353899:worko-cand-profile-parser-retry-queue-dev', 'awsRegion': 'ap-south-1'}]}
    # # event = {'Records': [{'eventVersion': '2.1', 'eventSource': 'aws:s3', 'awsRegion': 'ap-south-1', 'eventTime': '2026-03-13T09:19:34.588Z', 'eventName': 'ObjectCreated:Put', 'userIdentity': {'principalId': 'AWS:AROATCKANHWVXMDFRAEJE:worko-corp-dev-workoCorp'}, 'requestParameters': {'sourceIPAddress': '43.251.217.94'}, 'responseElements': {'x-amz-request-id': 'FG127W175PKRXRW6', 'x-amz-id-2': 'Rx0SJiCbbWvPYSXSOAT44aFmrQwG55QR+TPD9VNN82srRYoBslLCTV9UrVg2isJvgZEaOc+VlYIRmSraPzVDbmCXUmYZB249G24g33b4wb0='}, 's3': {'s3SchemaVersion': '1.0', 'configurationId': '7bf28bb9-cec6-40ba-8c21-819741898750', 'bucket': {'name': 'worko-corporate-cand-profile-dev', 'ownerIdentity': {'principalId': 'A1V0APDMR493SG'}, 'arn': 'arn:aws:s3:::worko-corporate-cand-profile-dev'}, 'object': {'key': 'companies/01KCGXV5WPA6C4S0PXFSMRQAQZ/bulk-cvs/01KKK7WTJHTXD7XAFN2DVE986F.pdf', 'size': 62202, 'eTag': '5278005910e63ff01980ac601156ddca', 'sequencer': '0069B3D6A68B7BF69C'}}}]}
    # # new s3->sqs flow triger
    # event ={'Records': [{'messageId': '4a4a2052-44f2-40b5-933e-715669f75f90', 'receiptHandle': 'AQEBWvogdwYEidoqhqak+7CSxbk1JSliRNJSsDbkZzfR5JwCSf1h8xTIgVMRHIX9on9WpOByVodQ6Iqng06hmOacvVejLvH2Xtnv9VXyscyPYsD+9iOPqbCdyVrrzaQmPh3kC/lg9NTcpZ5qAGDLtOVPxNWSRc+u9nkjP1WZ3JO3HZsRt4HLCVhvd+7yL+oeh+yssbNjoqS/yXBCqR1zb4jBc3Suvi8K4QQz8ljJ7nhrjvAO5fp4o3koZ4MCuopKW48U9ssbQydJey8Mtuqc3XeUd8v8m92wJR7OTYADh7aheFILaCBid20M3B0MtgEpE+OcRTedofHrIUgE7xZ7Qv5iMsw1pDbFNy9+zOLQg7zAUTxq1gxQJPdUJfs+I70SjLRpzQH35PE5v9qbrDWYCpLbXPzAqKx86C4c5SMWh+JBAMo=', 'body': '{"Records":[{"eventVersion":"2.1","eventSource":"aws:s3","awsRegion":"ap-south-1","eventTime":"2026-03-27T04:55:14.683Z","eventName":"ObjectCreated:Put","userIdentity":{"principalId":"AWS:AROATCKANHWVXMDFRAEJE:worko-corp-dev-workoCorp"},"requestParameters":{"sourceIPAddress":"202.94.161.178"},"responseElements":{"x-amz-request-id":"854QR7KXGVEEMHMC","x-amz-id-2":"kMw0WkzWD8dyHAyuSIAfljz75lO6leHxD/p+S+zGBmVBHeFCHcNl9lJltPXbQbkxPouzq0JYcsvooBQdc8+W+u8Toea8E2FxihSuxqgnxdk="},"s3":{"s3SchemaVersion":"1.0","configurationId":"sqs-event","bucket":{"name":"worko-corporate-cand-profile-dev","ownerIdentity":{"principalId":"A1V0APDMR493SG"},"arn":"arn:aws:s3:::worko-corporate-cand-profile-dev"},"object":{"key":"companies/01KCGXV5WPA6C4S0PXFSMRQAQZ/bulk-cvs/01KMPTB0680ST56TT9YZ6ECGDE.pdf","size":889010,"eTag":"a9806a8d905f21d2571b6a0dddbe4cb0","sequencer":"0069C60DB2A1507042"}}}]}', 'attributes': {'ApproximateReceiveCount': '1', 'SentTimestamp': '1774587315678', 'SenderId': 'AROAVASDGOGDX2TDMB5GG:S3-PROD-END', 'ApproximateFirstReceiveTimestamp': '1774587315684'}, 'messageAttributes': {}, 'md5OfBody': '15768f126aeb1e1a0d071e25ade50b08', 'eventSource': 'aws:sqs', 'eventSourceARN': 'arn:aws:sqs:ap-south-1:211125353899:worko-cand-profile-parser-queue-dev', 'awsRegion': 'ap-south-1'}]}
    # btache of 10 event

    # event ={
    # "Records": [
    #     {
    #     "messageId": "888e685d-b60d-46d4-8e6f-c624b7702cae",
    #     "receiptHandle": "AQEBPc6tw2K0EV3BAL9vGn3PsuD8FZyLh/CPOQmJviIT8HQ+Eh0NRfMA4lLE13bA7Rieg6h0dZMyxy8fGS8RAYsenyhoVxwR5KQ0MckiXORJNOZ+hV/eGUI6WctoqxH8rkZDKKaMtmDfn8sud5UNBOgNOWMHs3s/2YzM9wx5aBTxSWQy7wUOIXaydYhChIUN2pVjI9aTHxYyT7ci4KgDB40qeM9e1OFk33YsUwQVM8Z0nHoYsKJzWAHZxZMpw4eKOd37UV8vMu88g+gQYiIwZpdMinLQgx41u2bwV8GIuFI0ErzfssLcGYwPzAN2zj11IzPu+wH2beTuw4t5/hlxbLJ0IF8SdqYWv1b4M5HXQ5KKdTqQK0I8l3RtB07ZpS3EFYl7HmJTOqrsX133mXsvyLxORpPTaaMrP31XMT5J+cbBjAg=",
    #     "body": "{\"Records\":[{\"eventVersion\":\"2.1\",\"eventSource\":\"aws:s3\",\"awsRegion\":\"ap-south-1\",\"eventTime\":\"2026-04-01T08:27:12.092Z\",\"eventName\":\"ObjectCreated:Put\",\"userIdentity\":{\"principalId\":\"AWS:AROATCKANHWVXMDFRAEJE:worko-corp-dev-workoCorp\"},\"requestParameters\":{\"sourceIPAddress\":\"183.87.254.176\"},\"responseElements\":{\"x-amz-request-id\":\"TWZT4KYCXZHRRJ59\",\"x-amz-id-2\":\"sgl/IDYL5iPF/trzUAYAhw4V42g5FzISUyx1qZhy2vDyRnBW5TElaYND5IcD4vQqbbIRo2Z57Ee7QVU9wQ6w5AfTtyUuTrahp0ZWwjDvyWc=\"},\"s3\":{\"s3SchemaVersion\":\"1.0\",\"configurationId\":\"sqs-event-admin\",\"bucket\":{\"name\":\"worko-admin-cand-profile-dev\",\"ownerIdentity\":{\"principalId\":\"A1V0APDMR493SG\"},\"arn\":\"arn:aws:s3:::worko-admin-cand-profile-dev\"},\"object\":{\"key\":\"bulk-cvs/01KN42EMRBCGS1T5K6H8DC77AQ.pdf\",\"size\":241720,\"eTag\":\"8423cb3ac903e6640ddac3ee9d7136ad\",\"sequencer\":\"0069CCD6E0137665DF\"}}}]}",
    #     "attributes": {
    #         "ApproximateReceiveCount": "1",
    #         "SentTimestamp": "1775032032762",
    #         "SenderId": "AROAVASDGOGDX2TDMB5GG:S3-PROD-END",
    #         "ApproximateFirstReceiveTimestamp": "1775032032764"
    #     },
    #     "messageAttributes": {},
    #     "md5OfBody": "b198c48d0aa843c1fc8e252803e07420",
    #     "eventSource": "aws:sqs",
    #     "eventSourceARN": "arn:aws:sqs:ap-south-1:211125353899:worko-cand-profile-parser-queue-dev",
    #     "awsRegion": "ap-south-1"
    #     },
    #     {
    #     "messageId": "b290c4fe-ab76-4477-9af6-a5678f81224d",
    #     "receiptHandle": "AQEBEakYB3D4uV8ySsrnyNeDl3zyGNduXKKYRH6/b8qFH5iRJ1fFYxod1sFPNCsrw4+mZZKIqxH8Vikgl+bJVDwl1zgy5IUQ/r4c2p2TiV/QKFZllCwM3XpiFafiui4VRdbKiQX1C3b3oHGmCAmBKklZZ1BUgMoPxCl7VNHnykhW2hOK3Se59JwvGSeFXJmku/VaQVUM7zLFqu9ASiNxhsXDbXcs54LXCGkicWc/p3MMGpbLX0YLAfOVgkJG/2hQZWph7N0znoWX2YrWbuF8hhtdp4yDjjgMtRUxaw+Bp2Ttd6r5WHY3JS3e1db8UrKegKfjHxv0Fll7gT6oCUR84jZGf036PktQxLki9qV2JZIw6N9NSJDBasMLBMfAJRhW0xkagCo/NCC8MH6KFQ9sVZd0i9rZ1A96Jj9FR560dYI6DgM=",
    #     "body": "{\"Records\":[{\"eventVersion\":\"2.1\",\"eventSource\":\"aws:s3\",\"awsRegion\":\"ap-south-1\",\"eventTime\":\"2026-04-01T08:27:12.043Z\",\"eventName\":\"ObjectCreated:Put\",\"userIdentity\":{\"principalId\":\"AWS:AROATCKANHWVXMDFRAEJE:worko-corp-dev-workoCorp\"},\"requestParameters\":{\"sourceIPAddress\":\"183.87.254.176\"},\"responseElements\":{\"x-amz-request-id\":\"TWZWERG9N00P5B35\",\"x-amz-id-2\":\"OzgZKMUJPf2NTA2JGGHVm6rN0CBu+l0TWcn4dmjLPTLSMVqJMELnHrxyf716ZmlIiDxrOGFlF0nCzzmtd6ttGg3N+0bIUU0SP3bWaQi+PK4=\"},\"s3\":{\"s3SchemaVersion\":\"1.0\",\"configurationId\":\"sqs-event-admin\",\"bucket\":{\"name\":\"worko-admin-cand-profile-dev\",\"ownerIdentity\":{\"principalId\":\"A1V0APDMR493SG\"},\"arn\":\"arn:aws:s3:::worko-admin-cand-profile-dev\"},\"object\":{\"key\":\"bulk-cvs/01KN42EMRC8DGFM7S2FSM6HKEZ.pdf\",\"size\":6727,\"eTag\":\"ffef798071f9c87a48c942bd88b75990\",\"sequencer\":\"0069CCD6E0039C47C9\"}}}]}",
    #     "attributes": {
    #         "ApproximateReceiveCount": "1",
    #         "SentTimestamp": "1775032032759",
    #         "SenderId": "AROAVASDGOGDX2TDMB5GG:S3-PROD-END",
    #         "ApproximateFirstReceiveTimestamp": "1775032032765"
    #     },
    #     "messageAttributes": {},
    #     "md5OfBody": "6937c756b515e5f02c4f03ad9f7c8c80",
    #     "eventSource": "aws:sqs",
    #     "eventSourceARN": "arn:aws:sqs:ap-south-1:211125353899:worko-cand-profile-parser-queue-dev",
    #     "awsRegion": "ap-south-1"
    #     },
    #     {
    #     "messageId": "92471e0a-f434-42b9-845e-89727b5b9c59",
    #     "receiptHandle": "AQEBXCkW6ttTntVLgyQn2FCilDQO6488gsucJZYqo9tzr6Vfr8D6AqGV0UopJ11JsgQaFB+tqE+9XYIbjqTEmjCgkRKJ2/AQu9ioBTiJuXbZnpxDTwYfkYYZONIRSm0wZGCiHWKc3insebgxpj5bBORFQkfU+8WjITZaFgPwk2EDq09SsJn6jpMrkoBQ41E5pmsB5hjywJGy2l/+jxE3HHCDUCXuQtPiWWQ4h8YafKQzskPsiiXZlpc7d6TvupzLDV9XYnR61gNgaVtOnkpb1LT4aEP9PfbpBilWjymRtSZqeL0Io0wST5mhLXDd+l20ZQmMxGYhCfgb3eiAZgrqZg1lHOyzjmS4j1RV0ZwmCpw6l6Gz3RXP2bxkNlRrR+rHWlV7/WGm0hFfP3XKgeQErnaG6QSDl5uYuEa5G9RBdj03xYQ=",
    #     "body": "{\"Records\":[{\"eventVersion\":\"2.1\",\"eventSource\":\"aws:s3\",\"awsRegion\":\"ap-south-1\",\"eventTime\":\"2026-04-01T08:27:12.222Z\",\"eventName\":\"ObjectCreated:Put\",\"userIdentity\":{\"principalId\":\"AWS:AROATCKANHWVXMDFRAEJE:worko-corp-dev-workoCorp\"},\"requestParameters\":{\"sourceIPAddress\":\"183.87.254.176\"},\"responseElements\":{\"x-amz-request-id\":\"TWZZ0VC02AVY1XWQ\",\"x-amz-id-2\":\"nAFcxcLMR5+rJuZtKv8nVGWryT71vBW3zyn37K8upmsniuyvgJmJo6aEJxgNU+m9+m2sPiOUMjH3PsAUb58X8SgNwJciy1VzeQCejTtEvGU=\"},\"s3\":{\"s3SchemaVersion\":\"1.0\",\"configurationId\":\"sqs-event-admin\",\"bucket\":{\"name\":\"worko-admin-cand-profile-dev\",\"ownerIdentity\":{\"principalId\":\"A1V0APDMR493SG\"},\"arn\":\"arn:aws:s3:::worko-admin-cand-profile-dev\"},\"object\":{\"key\":\"bulk-cvs/01KN42EMRCJEZYF20SVT5RFHB7.pdf\",\"size\":221340,\"eTag\":\"0f5f0eb793b027f8c1be25cfeade2baf\",\"sequencer\":\"0069CCD6E031AB55E3\"}}}]}",
    #     "attributes": {
    #         "ApproximateReceiveCount": "1",
    #         "SentTimestamp": "1775032032760",
    #         "SenderId": "AROAVASDGOGDX2TDMB5GG:S3-PROD-END",
    #         "ApproximateFirstReceiveTimestamp": "1775032032765"
    #     },
    #     "messageAttributes": {},
    #     "md5OfBody": "89448abb06910bf345fa5349353dfd82",
    #     "eventSource": "aws:sqs",
    #     "eventSourceARN": "arn:aws:sqs:ap-south-1:211125353899:worko-cand-profile-parser-queue-dev",
    #     "awsRegion": "ap-south-1"
    #     },
    #     {
    #     "messageId": "25af44d5-bf20-4e30-b3ea-9f91699cb13b",
    #     "receiptHandle": "AQEBPDtcpo3Y9x5pRvlGJzeTRW/gmape95vZOg0yULmpDTlueyoLFdi47FoC9uKwP5LCAso/7scu3gHwnt9YP9amzQ8xrkkmeATEMUYu/kE3YFs5Kg6/r9yJ5mYU3cNsD3TfUurKoKAac/qMV+X03nCGj2bALLFQvivx+xa8nxGnK1bM5K5xzG4E+3FQm7uNeMcwAvyegk+D/yiuKaakXG16CDdYKO45f2HZn9T/2ttUhgJPXMwOa/9JltoN/VraSLaio+H1+3jeFFMflAWW4zL+UqdrW3nfo910P4ga7Mafsl6cfJlaadmWXD8BSolMIM6mbE087xWSZoX7eBhh7KZk6nXEPf9Z1p8fe70G/PKCFhvahqtOsRW+8LhLpUAHwz4THIQRJI2k2k0Dprr5kcWYg6tyJMlGrKlODKRzc/OvF7o=",
    #     "body": "{\"Records\":[{\"eventVersion\":\"2.1\",\"eventSource\":\"aws:s3\",\"awsRegion\":\"ap-south-1\",\"eventTime\":\"2026-04-01T08:27:11.910Z\",\"eventName\":\"ObjectCreated:Put\",\"userIdentity\":{\"principalId\":\"AWS:AROATCKANHWVXMDFRAEJE:worko-corp-dev-workoCorp\"},\"requestParameters\":{\"sourceIPAddress\":\"183.87.254.176\"},\"responseElements\":{\"x-amz-request-id\":\"R7VMS9Q9FSD5HW73\",\"x-amz-id-2\":\"O6CvBqqpREf/WND21b/WB8Kp88Pcn/1bjOyCeyhGXLQVnqpRgLKrA7Me+GFcEmMLSdIZNFmKZa2Bizln+OUgqiCjUShK4SLoANfibbLlbOA=\"},\"s3\":{\"s3SchemaVersion\":\"1.0\",\"configurationId\":\"sqs-event-admin\",\"bucket\":{\"name\":\"worko-admin-cand-profile-dev\",\"ownerIdentity\":{\"principalId\":\"A1V0APDMR493SG\"},\"arn\":\"arn:aws:s3:::worko-admin-cand-profile-dev\"},\"object\":{\"key\":\"bulk-cvs/01KN42EMRCFF62MYQMNR2Z7XE6.pdf\",\"size\":204675,\"eTag\":\"6936cf44c080f79c528678b96b6c7567\",\"sequencer\":\"0069CCD6DFDBEDD0CE\"}}}]}",
    #     "attributes": {
    #         "ApproximateReceiveCount": "1",
    #         "SentTimestamp": "1775032032761",
    #         "SenderId": "AROAVASDGOGDX2TDMB5GG:S3-PROD-END",
    #         "ApproximateFirstReceiveTimestamp": "1775032032765"
    #     },
    #     "messageAttributes": {},
    #     "md5OfBody": "bb2ba77b3c4e4142a0e63c028b48b2c3",
    #     "eventSource": "aws:sqs",
    #     "eventSourceARN": "arn:aws:sqs:ap-south-1:211125353899:worko-cand-profile-parser-queue-dev",
    #     "awsRegion": "ap-south-1"
    #     }
    # ]
    # }
    #btahc of 10 sqs event
    # event = {
    #     "Records": [
    #         {
    #         "messageId": "f02f0854-2adb-4b52-ad34-421b871875c7",
    #         "receiptHandle": "AQEB8AflVF3Shy1N6piIlAiKZS3m4dW6yZqGrTIxcVAsuqRujZmo2QAnLml+fYZg6NHNN90cLsVY35nCWgNHnRCO9W7/HeuSwBZvRsdh8Df3La8T0+7GnAm2ClvcklqAyec2kZ5LhXIIkn/3HShh4/t7XK7BoHV6JtI4qFI2r6BpeiIi5DqPXGKvu6/wixHGnldQPnLn8xq3+W4k29aiIAI26qFaHrUfs0w4p7PRUZe70UCG7epMaYy0dN1Y6D/Y+45/Mtvn7SN4EvUzuoxqZwpoMz7ORpFVWmxZ7MseaFgF5x6LYKHPWXQOT1LIejZguvnSwhwUXpZmXG5mwIvTgpw+DP0GoO6pzPqCG+1NEToJMKevJR6WPeDqV8uPitnP5p/Nnz7SfLkFsZFDujxJGrgLrJC5TI0Z7vys+s33Pdo8sNtq8W5ydswoe9aoOMmE1ZRe",
    #         "body": "{\"retry_counter\":1,\"eventType\":\"RetrySQS\",\"records\":[{\"messageId\":\"b290c4fe-ab76-4477-9af6-a5678f81224d\",\"receiptHandle\":\"AQEBEakYB3D4uV8ySsrnyNeDl3zyGNduXKKYRH6/b8qFH5iRJ1fFYxod1sFPNCsrw4+mZZKIqxH8Vikgl+bJVDwl1zgy5IUQ/r4c2p2TiV/QKFZllCwM3XpiFafiui4VRdbKiQX1C3b3oHGmCAmBKklZZ1BUgMoPxCl7VNHnykhW2hOK3Se59JwvGSeFXJmku/VaQVUM7zLFqu9ASiNxhsXDbXcs54LXCGkicWc/p3MMGpbLX0YLAfOVgkJG/2hQZWph7N0znoWX2YrWbuF8hhtdp4yDjjgMtRUxaw+Bp2Ttd6r5WHY3JS3e1db8UrKegKfjHxv0Fll7gT6oCUR84jZGf036PktQxLki9qV2JZIw6N9NSJDBasMLBMfAJRhW0xkagCo/NCC8MH6KFQ9sVZd0i9rZ1A96Jj9FR560dYI6DgM=\",\"body\":\"{\\\"Records\\\":[{\\\"eventVersion\\\":\\\"2.1\\\",\\\"eventSource\\\":\\\"aws:s3\\\",\\\"awsRegion\\\":\\\"ap-south-1\\\",\\\"eventTime\\\":\\\"2026-04-01T08:27:12.043Z\\\",\\\"eventName\\\":\\\"ObjectCreated:Put\\\",\\\"userIdentity\\\":{\\\"principalId\\\":\\\"AWS:AROATCKANHWVXMDFRAEJE:worko-corp-dev-workoCorp\\\"},\\\"requestParameters\\\":{\\\"sourceIPAddress\\\":\\\"183.87.254.176\\\"},\\\"responseElements\\\":{\\\"x-amz-request-id\\\":\\\"TWZWERG9N00P5B35\\\",\\\"x-amz-id-2\\\":\\\"OzgZKMUJPf2NTA2JGGHVm6rN0CBu+l0TWcn4dmjLPTLSMVqJMELnHrxyf716ZmlIiDxrOGFlF0nCzzmtd6ttGg3N+0bIUU0SP3bWaQi+PK4=\\\"},\\\"s3\\\":{\\\"s3SchemaVersion\\\":\\\"1.0\\\",\\\"configurationId\\\":\\\"sqs-event-admin\\\",\\\"bucket\\\":{\\\"name\\\":\\\"worko-admin-cand-profile-dev\\\",\\\"ownerIdentity\\\":{\\\"principalId\\\":\\\"A1V0APDMR493SG\\\"},\\\"arn\\\":\\\"arn:aws:s3:::worko-admin-cand-profile-dev\\\"},\\\"object\\\":{\\\"key\\\":\\\"bulk-cvs/01KN42EMRC8DGFM7S2FSM6HKEZ.pdf\\\",\\\"size\\\":6727,\\\"eTag\\\":\\\"ffef798071f9c87a48c942bd88b75990\\\",\\\"sequencer\\\":\\\"0069CCD6E0039C47C9\\\"}}}]}\"},{\"messageId\":\"92471e0a-f434-42b9-845e-89727b5b9c59\",\"receiptHandle\":\"AQEBXCkW6ttTntVLgyQn2FCilDQO6488gsucJZYqo9tzr6Vfr8D6AqGV0UopJ11JsgQaFB+tqE+9XYIbjqTEmjCgkRKJ2/AQu9ioBTiJuXbZnpxDTwYfkYYZONIRSm0wZGCiHWKc3insebgxpj5bBORFQkfU+8WjITZaFgPwk2EDq09SsJn6jpMrkoBQ41E5pmsB5hjywJGy2l/+jxE3HHCDUCXuQtPiWWQ4h8YafKQzskPsiiXZlpc7d6TvupzLDV9XYnR61gNgaVtOnkpb1LT4aEP9PfbpBilWjymRtSZqeL0Io0wST5mhLXDd+l20ZQmMxGYhCfgb3eiAZgrqZg1lHOyzjmS4j1RV0ZwmCpw6l6Gz3RXP2bxkNlRrR+rHWlV7/WGm0hFfP3XKgeQErnaG6QSDl5uYuEa5G9RBdj03xYQ=\",\"body\":\"{\\\"Records\\\":[{\\\"eventVersion\\\":\\\"2.1\\\",\\\"eventSource\\\":\\\"aws:s3\\\",\\\"awsRegion\\\":\\\"ap-south-1\\\",\\\"eventTime\\\":\\\"2026-04-01T08:27:12.222Z\\\",\\\"eventName\\\":\\\"ObjectCreated:Put\\\",\\\"userIdentity\\\":{\\\"principalId\\\":\\\"AWS:AROATCKANHWVXMDFRAEJE:worko-corp-dev-workoCorp\\\"},\\\"requestParameters\\\":{\\\"sourceIPAddress\\\":\\\"183.87.254.176\\\"},\\\"responseElements\\\":{\\\"x-amz-request-id\\\":\\\"TWZZ0VC02AVY1XWQ\\\",\\\"x-amz-id-2\\\":\\\"nAFcxcLMR5+rJuZtKv8nVGWryT71vBW3zyn37K8upmsniuyvgJmJo6aEJxgNU+m9+m2sPiOUMjH3PsAUb58X8SgNwJciy1VzeQCejTtEvGU=\\\"},\\\"s3\\\":{\\\"s3SchemaVersion\\\":\\\"1.0\\\",\\\"configurationId\\\":\\\"sqs-event-admin\\\",\\\"bucket\\\":{\\\"name\\\":\\\"worko-admin-cand-profile-dev\\\",\\\"ownerIdentity\\\":{\\\"principalId\\\":\\\"A1V0APDMR493SG\\\"},\\\"arn\\\":\\\"arn:aws:s3:::worko-admin-cand-profile-dev\\\"},\\\"object\\\":{\\\"key\\\":\\\"bulk-cvs/01KN42EMRCJEZYF20SVT5RFHB7.pdf\\\",\\\"size\\\":221340,\\\"eTag\\\":\\\"0f5f0eb793b027f8c1be25cfeade2baf\\\",\\\"sequencer\\\":\\\"0069CCD6E031AB55E3\\\"}}}]}\"},{\"messageId\":\"25af44d5-bf20-4e30-b3ea-9f91699cb13b\",\"receiptHandle\":\"AQEBPDtcpo3Y9x5pRvlGJzeTRW/gmape95vZOg0yULmpDTlueyoLFdi47FoC9uKwP5LCAso/7scu3gHwnt9YP9amzQ8xrkkmeATEMUYu/kE3YFs5Kg6/r9yJ5mYU3cNsD3TfUurKoKAac/qMV+X03nCGj2bALLFQvivx+xa8nxGnK1bM5K5xzG4E+3FQm7uNeMcwAvyegk+D/yiuKaakXG16CDdYKO45f2HZn9T/2ttUhgJPXMwOa/9JltoN/VraSLaio+H1+3jeFFMflAWW4zL+UqdrW3nfo910P4ga7Mafsl6cfJlaadmWXD8BSolMIM6mbE087xWSZoX7eBhh7KZk6nXEPf9Z1p8fe70G/PKCFhvahqtOsRW+8LhLpUAHwz4THIQRJI2k2k0Dprr5kcWYg6tyJMlGrKlODKRzc/OvF7o=\",\"body\":\"{\\\"Records\\\":[{\\\"eventVersion\\\":\\\"2.1\\\",\\\"eventSource\\\":\\\"aws:s3\\\",\\\"awsRegion\\\":\\\"ap-south-1\\\",\\\"eventTime\\\":\\\"2026-04-01T08:27:11.910Z\\\",\\\"eventName\\\":\\\"ObjectCreated:Put\\\",\\\"userIdentity\\\":{\\\"principalId\\\":\\\"AWS:AROATCKANHWVXMDFRAEJE:worko-corp-dev-workoCorp\\\"},\\\"requestParameters\\\":{\\\"sourceIPAddress\\\":\\\"183.87.254.176\\\"},\\\"responseElements\\\":{\\\"x-amz-request-id\\\":\\\"R7VMS9Q9FSD5HW73\\\",\\\"x-amz-id-2\\\":\\\"O6CvBqqpREf/WND21b/WB8Kp88Pcn/1bjOyCeyhGXLQVnqpRgLKrA7Me+GFcEmMLSdIZNFmKZa2Bizln+OUgqiCjUShK4SLoANfibbLlbOA=\\\"},\\\"s3\\\":{\\\"s3SchemaVersion\\\":\\\"1.0\\\",\\\"configurationId\\\":\\\"sqs-event-admin\\\",\\\"bucket\\\":{\\\"name\\\":\\\"worko-admin-cand-profile-dev\\\",\\\"ownerIdentity\\\":{\\\"principalId\\\":\\\"A1V0APDMR493SG\\\"},\\\"arn\\\":\\\"arn:aws:s3:::worko-admin-cand-profile-dev\\\"},\\\"object\\\":{\\\"key\\\":\\\"bulk-cvs/01KN42EMRCFF62MYQMNR2Z7XE6.pdf\\\",\\\"size\\\":204675,\\\"eTag\\\":\\\"6936cf44c080f79c528678b96b6c7567\\\",\\\"sequencer\\\":\\\"0069CCD6DFDBEDD0CE\\\"}}}]}\"}]}",
    #         "attributes": {
    #             "ApproximateReceiveCount": "1",
    #             "SentTimestamp": "1775040395164",
    #             "SenderId": "AROATCKANHWVTQO36WAQQ:shaukat.shaikh@worko.ai",
    #             "ApproximateFirstReceiveTimestamp": "1775040485164"
    #         },
    #         "messageAttributes": {},
    #         "md5OfBody": "5d09db51cc1483e1d1fa17c92d0cc54a",
    #         "eventSource": "aws:sqs",
    #         "eventSourceARN": "arn:aws:sqs:ap-south-1:211125353899:worko-cand-profile-parser-retry-queue-dev",
    #         "awsRegion": "ap-south-1"
    #         }
    #     ]
    #     }
    
    # #s3
    # event = {'Records': [{'messageId': 'a130c11c-620f-45c5-83f0-9adfd40e0469', 'receiptHandle': 'AQEBjBqKam59tWsoE9+T0W8Khm1oxuAiEbdXZsmUfvEmk050KGh6Azn9Ifcs1Hq2PcyFnNFYKm3odxD6zA9sAkqyHGIeQF0cd88ZySZoPo+hGkIZil9UBbHVNwwx8u3YWsugIAxyZyj1ir30G7Pj93zEh2jfccSIACy/cE0bsBUJ34UHtF8vIGzHfGcer66xBJDZI1c+DKOIClxjGdzUQegrBHGxZEdnSoq3Gr5ORRzAViPM7NUbAO0K42ftc2tmZqhS5VCTUEuUKmqcbSd/raob5WsACZgFas+Xeocx1PttzWELoNBA8hyPL6MQYFQPv0KrjvxYIt2TgVCSaClq3YkOEBFHQ4IKWBuJgloafbCO+KrSSy9mk4galQIz/eP5ynRV5qUX8wiPjQ3n6R9tkmcpdK+OOMXMMo9Czw1NgnXlKwo=', 'body': '{"Records":[{"eventVersion":"2.1","eventSource":"aws:s3","awsRegion":"ap-south-1","eventTime":"2026-04-02T02:07:40.555Z","eventName":"ObjectCreated:Put","userIdentity":{"principalId":"AWS:AROATCKANHWVXMDFRAEJE:worko-corp-dev-workoCorp"},"requestParameters":{"sourceIPAddress":"183.87.254.176"},"responseElements":{"x-amz-request-id":"35PE95VWGS3MEXAJ","x-amz-id-2":"FE9huMj517jZJulH3U1/lyehQ+l6G9BSneIqfEZaq7UMsGqJxTBgWj3MgMbd59w2g5D4w9YEv8dL3Vgsv6bNjsVQXyxKId6QXwtTjQSCdkQ="},"s3":{"s3SchemaVersion":"1.0","configurationId":"sqs-event-corporate","bucket":{"name":"worko-corporate-cand-profile-dev","ownerIdentity":{"principalId":"A1V0APDMR493SG"},"arn":"arn:aws:s3:::worko-corporate-cand-profile-dev"},"object":{"key":"companies/01JNR4N624Q7E8XH9X8G9MNH62/bulk-cvs/01KN5Z4FNB0JA2GAE9R9MASF8H.pdf","size":187438,"eTag":"3208a3565002d05e552b50232cdca634","sequencer":"0069CDCF6C831D28C2"}}}]}', 'attributes': {'ApproximateReceiveCount': '1', 'SentTimestamp': '1775095661601', 'SenderId': 'AROAVASDGOGDX2TDMB5GG:S3-PROD-END', 'ApproximateFirstReceiveTimestamp': '1775095661604'}, 'messageAttributes': {}, 'md5OfMessageAttributes': None, 'md5OfBody': 'f16019f9932a891b2049cedc7b695a19', 'eventSource': 'aws:sqs', 'eventSourceARN': 'arn:aws:sqs:ap-south-1:211125353899:worko-cand-profile-parser-queue-dev', 'awsRegion': 'ap-south-1'}, {'messageId': '9006f331-60f8-4b7a-9056-fb2eac039dbc', 'receiptHandle': 'AQEBA6KDz1PRrMeDFdpRUyuzJVaVXE53CmOMyrQN1h+Edm+EGuW8773fTl/X9Tn7qFb1t8idZJKvuPm4vLzF+ZaVr+IvUpD+XDWJiMNnUAE276xKprFpgi9h7ov1+Fp4xs3Yg7Aq1ZQ+lX0sSOJCAhlvzd63KQIh0lpnLNSVxrh2x/Fpk+1nnPWDsP3nYfqWlI/zpMjt/2qMcHJSlA9pEdtst4+De2mzbkb6QUciL2iSml/2/mPALpkrTING3mQXuqRp/33TKVB/EajSGTaDR+7k0X9C9ghcFnmjwOxG2V1Ss75aHjmD2/ONNTRKJNwGO07YQ8OiXsRJkUtrO3ntiRRovba6wGb+gsWEw0GklfY1gSLqB/xoaItT3HU2Js4sJHplxLzik0cqgxr2bS1bPeQwlqzcRQZrpvnLGzzzlz8eOaQ=', 'body': '{"Records":[{"eventVersion":"2.1","eventSource":"aws:s3","awsRegion":"ap-south-1","eventTime":"2026-04-02T02:07:40.586Z","eventName":"ObjectCreated:Put","userIdentity":{"principalId":"AWS:AROATCKANHWVXMDFRAEJE:worko-corp-dev-workoCorp"},"requestParameters":{"sourceIPAddress":"183.87.254.176"},"responseElements":{"x-amz-request-id":"35PA7Z4EJX3W5ZDS","x-amz-id-2":"BjHFu5DEt+tFs1TbjSxHudFoQmo5KkriHtDpGj+thbqUbU4veeVYlXbVyufR9fOQXre3agCXePpxOxpHXToxC0cxLluNt9AI3uNCc4v+62c="},"s3":{"s3SchemaVersion":"1.0","configurationId":"sqs-event-corporate","bucket":{"name":"worko-corporate-cand-profile-dev","ownerIdentity":{"principalId":"A1V0APDMR493SG"},"arn":"arn:aws:s3:::worko-corporate-cand-profile-dev"},"object":{"key":"companies/01JNR4N624Q7E8XH9X8G9MNH62/bulk-cvs/01KN5Z4FNCR663FRTEFJM5ZYQP.pdf","size":225470,"eTag":"b92b80d17b604743574cdcfcc3ec4fe2","sequencer":"0069CDCF6C89EF8975"}}}]}', 'attributes': {'ApproximateReceiveCount': '1', 'SentTimestamp': '1775095661597', 'SenderId': 'AROAVASDGOGDX2TDMB5GG:S3-PROD-END', 'ApproximateFirstReceiveTimestamp': '1775095661600'}, 'messageAttributes': {}, 'md5OfMessageAttributes': None, 'md5OfBody': '587c9606b9d18abf52bc4c231d0b7b54', 'eventSource': 'aws:sqs', 'eventSourceARN': 'arn:aws:sqs:ap-south-1:211125353899:worko-cand-profile-parser-queue-dev', 'awsRegion': 'ap-south-1'}, {'messageId': '338371da-285a-4669-b5cf-dc040999305f', 'receiptHandle': 'AQEBc8rp4KnKLzonOlSIJGIoyXbW63vAoJwALk0zSOOIfo85Mt55Pcd53LhrBqR6cz6sxQTrQxkX9MVq6yo88dfr6PAYecpMk4Kmig0yGpGxWIp1ikLtzGkMCk/bH3DTkClJhsfM9EEfzMmfyMwa3yTAgMhjAqG6v9WCaIix/kl75M986+2qUh5i7pMdKK/BiT5iVXg69yRAloisy52a3g2hPxaAa8/RWuADiTo/4lPycrrDxiFhgLYVR4skQ/t+mYHuT5EPjT6UL6C3Nl6ekvbgndxl3nDmGf3GSgHIvZ1uuRCKwFfUAPw5yFK58iSmGOHhSy3GEIS4YPXgCwI5eo2cL22IKlYecH9dTL4PXpQOR8vBWt3wfXaVpsJjnPdJ4HANe+m3f2aw+eiSfru7SZ6GhZJPYeM1VMTz5pHBthwfaN8=', 'body': '{"Records":[{"eventVersion":"2.1","eventSource":"aws:s3","awsRegion":"ap-south-1","eventTime":"2026-04-02T02:07:40.559Z","eventName":"ObjectCreated:Put","userIdentity":{"principalId":"AWS:AROATCKANHWVXMDFRAEJE:worko-corp-dev-workoCorp"},"requestParameters":{"sourceIPAddress":"183.87.254.176"},"responseElements":{"x-amz-request-id":"35PBSJBB71PFW6KZ","x-amz-id-2":"DDtFYMi7E11HUtr/Un6YGCaR2l8HnQ9txhCtZvN87SNBUiSfJt0kFSOnm8irsnea8LdABbZby1AFdengHFqB3rfIAmLKCEjugbV9YZTONYQ="},"s3":{"s3SchemaVersion":"1.0","configurationId":"sqs-event-corporate","bucket":{"name":"worko-corporate-cand-profile-dev","ownerIdentity":{"principalId":"A1V0APDMR493SG"},"arn":"arn:aws:s3:::worko-corporate-cand-profile-dev"},"object":{"key":"companies/01JNR4N624Q7E8XH9X8G9MNH62/bulk-cvs/01KN5Z4FNCC45360G3JK2W076W.pdf","size":167286,"eTag":"51d9846cd02ac6aa0c450d18502692ef","sequencer":"0069CDCF6C843BC33C"}}}]}', 'attributes': {'ApproximateReceiveCount': '1', 'SentTimestamp': '1775095661602', 'SenderId': 'AROAVASDGOGDX2TDMB5GG:S3-PROD-END', 'ApproximateFirstReceiveTimestamp': '1775095661603'}, 'messageAttributes': {}, 'md5OfMessageAttributes': None, 'md5OfBody': 'b8a13d76b1ff314f28d53bed6b0a8b34', 'eventSource': 'aws:sqs', 'eventSourceARN': 'arn:aws:sqs:ap-south-1:211125353899:worko-cand-profile-parser-queue-dev', 'awsRegion': 'ap-south-1'}]}
    # lambda_handler(event, None)