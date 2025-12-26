added Azure secrect- 
1) needs to create "AZURE-openai-secret-{env}" (using from secret manager instead of making it env variables)
2) extra permission to get it from secrect manager
3) removed Azure keys from env variables
4) name changed from worko-bulk-jd-resume-matching to worko-bulk-jd-resume-matching +env 