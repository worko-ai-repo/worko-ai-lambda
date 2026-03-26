added Azure secrect- 
0) create AZURE-openai-secret-multimodel-{env} (new)
1) needs to create "AZURE-openai-secret-{env}" (using from secret manager instead of making it env variables)
2) extra permission to get it from secrect manager
3) removed Azure keys from env variables
4) name changed from worko-bulk-jd-resume-matching to worko-bulk-jd-resume-matching +env 

09/03/2026
added this line in the prompt
f" candidateLocation must be only city name followed by state name examples. Mumbai, Maharahstra,  Bengaluru Karnataka"
