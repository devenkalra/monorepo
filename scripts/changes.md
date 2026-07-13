1. Add a table to track logical volume names to physical paths as follows
    1. Create a table to track volumes that maps volume name like "Photo" to the mounted path and the path in the src file system
    1. Create a script to query the volume mapping and update by specifying the locally mounted path "p:/" and the src file system path (/volume1/photo)
    1. Update each script to take the name of the volume and extract the mounted path rather than taking it from the command line
    1. The files table should store the relative path from the src mount point

1. Add other file types besides video and images in the following way
    1. Add ability to track audio similar to video but only need audio track meta data
    1. For text oriented document files, use an ai service to find summary and store it in its meta data. 
    1. For text files create a thumbnail showing the first page
    1. For eml files, store the email relevant data 

3. Infrastructure improvements
  1. Enable text search on file names, summaries and text based meta data fields for media files


