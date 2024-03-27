#!/bin/bash
# Since plex is having such great troubles deleting files I wrote this little bash script to read the decisions.log and delete the files after it's been run.

inputfile=$1
while read -r line
do
         if [[ "$line" == *"Removing : {"* ]]; then
            # Original Regex
            # var=$(echo "${line}" | grep Removing | sed 's/^.*\(file.*multipart\).*$/\1/' | sed -r 's/^.{9}//' | sed 's/.\{14\}$//')
            
            # Updated Regex
            var=$(echo "${line}" | grep Removing | sed -E "s/.*'file': \['(.*)'\].*/\1/")
            echo "${var}"
            rm "${var}"
         fi
done < "$inputfile"
