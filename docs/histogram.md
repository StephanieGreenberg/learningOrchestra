# Histogram microservice
Microservice used to makes the histogram from a stored file, storing the result 
in a new file in MongoDB.

## Create a Histogram from inserted file
`POST CLUSTER_IP:5004/histograms/<filename>`

The request is sent in body, histrogram_filename is the filename to save the 
histogram result and fields are an array with all fields to make the 
histogram.

```json
{
    "histogram_filename": "filename_to_save_the_histogram",
    "fields": ["fields", "from", "filename"]
}
```
