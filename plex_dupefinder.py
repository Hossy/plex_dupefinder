#!/usr/bin/env python3
import collections
import itertools
import logging
import os
import sys
import time
import argparse
from fnmatch import fnmatch

from tabulate import tabulate

from config import cfg

try:
    from urlparse import urljoin
except ImportError:
    from urllib.parse import urljoin

from plexapi.server import PlexServer
import requests

############################################################
# INIT
############################################################

# Setup logger
log_filename = os.path.join(os.path.dirname(os.path.realpath(sys.argv[0])), 'activity.log')
logging.basicConfig(
    filename=log_filename,
    level=logging.DEBUG,
    format='[%(asctime)s] %(levelname)s - %(message)s',
    datefmt='%H:%M:%S'
)
logging.getLogger('urllib3.connectionpool').disabled = True
log = logging.getLogger("Plex_Dupefinder")

# Setup PlexServer object
try:
    plex = PlexServer(cfg['PLEX_SERVER'], cfg['PLEX_TOKEN'])
except:
    log.exception("Exception connecting to server %r with token %r", cfg['PLEX_SERVER'], cfg['PLEX_TOKEN'])
    print(f"Exception connecting to {cfg['PLEX_SERVER']} with token: {cfg['PLEX_TOKEN']}")

    exit(1)


############################################################
# PLEX METHODS
############################################################


def get_dupes(plex_section_name):
    sec_type = get_section_type(plex_section_name)
    dupe_search_results = plex.library.section(plex_section_name).search(duplicate=True, libtype=sec_type)

    dupe_search_results_new = dupe_search_results.copy()
    if cfg['FIND_DUPLICATE_FILEPATHS_ONLY']:
        for dupe in dupe_search_results:
            if any(x != dupe.locations[0] for x in dupe.locations):
                dupe_search_results_new.remove(dupe)
    return dupe_search_results_new


def get_section_type(plex_section_name):
    try:
        plex_section_type = plex.library.section(plex_section_name).type
    except Exception:
        log.exception("Exception occurred while trying to lookup the section type for Library: %s", plex_section_name)
        exit(1)
    return 'episode' if plex_section_type == 'show' else 'movie'


def get_score(media_info):
    score = 0
    # score audio codec
    for codec, codec_score in cfg['AUDIO_CODEC_SCORES'].items():
        if codec.lower() == media_info['audio_codec'].lower():
            score += int(codec_score)
            log.debug("Added %d to score for audio_codec being %r", int(codec_score), str(codec))
            break
    # score video codec
    for codec, codec_score in cfg['VIDEO_CODEC_SCORES'].items():
        if codec.lower() == media_info['video_codec'].lower():
            score += int(codec_score)
            log.debug("Added %d to score for video_codec being %r", int(codec_score), str(codec))
            break
    # score video resolution
    for resolution, resolution_score in cfg['VIDEO_RESOLUTION_SCORES'].items():
        if resolution.lower() == media_info['video_resolution'].lower():
            score += int(resolution_score)
            log.debug("Added %d to score for video_resolution being %r", int(resolution_score), str(resolution))
            break
    # score filename
    for filename_keyword, keyword_score in cfg['FILENAME_SCORES'].items():
        for filename in media_info['file']:
            if fnmatch(os.path.basename(filename.lower()), filename_keyword.lower()):
                score += int(keyword_score)
                log.debug("Added %d to score for match filename_keyword %s", int(keyword_score), filename_keyword)
    # add bitrate to score
    if cfg['SCORE_VIDEOBITRATE']:
        score += int(media_info['video_bitrate']) * 2
        log.debug("Added %d to score for video bitrate", int(media_info['video_bitrate']) * 2)
    # add duration to score
    score += int(media_info['video_duration']) / 300
    log.debug("Added %d to score for video duration", int(media_info['video_duration']) / 300)
    # add width to score
    score += int(media_info['video_width']) * 2
    log.debug("Added %d to score for video width", int(media_info['video_width']) * 2)
    # add height to score
    score += int(media_info['video_height']) * 2
    log.debug("Added %d to score for video height", int(media_info['video_height']) * 2)
    # add audio channels to score
    if cfg['SCORE_AUDIOCHANNELS']:
        score += int(media_info['audio_channels']) * 1000
        log.debug("Added %d to score for audio channels", int(media_info['audio_channels']) * 1000)
    # add file size to score
    if cfg['SCORE_FILESIZE']:
        score += int(media_info['file_size']) / 100000
        log.debug("Added %d to score for total file size", int(media_info['file_size']) / 100000)
    return int(score)


def get_media_info(item):
    info = {
        'id': 'Unknown',
        'video_bitrate': 0,
        'audio_codec': 'Unknown',
        'audio_channels': 0,
        'video_codec': 'Unknown',
        'video_resolution': 'Unknown',
        'video_width': 0,
        'video_height': 0,
        'video_duration': 0,
        'file': [],
        'multipart': False,
        'file_exists': True,  # Used with FIND_UNAVAILABLE
        'file_exts': {},      # Used with FIND_EXTRA_TS; It is an array whose keys are the file extensions and whose values are the count of media with that file extension
        'file_size': 0
    }
    # get id
    try:
        info['id'] = item.id
    except AttributeError:
        log.debug("Media item has no id")
    # get bitrate
    try:
        info['video_bitrate'] = item.bitrate if item.bitrate else 0
    except AttributeError:
        log.debug("Media item has no bitrate")
    # get video codec
    try:
        info['video_codec'] = item.videoCodec if item.videoCodec else 'Unknown'
    except AttributeError:
        log.debug("Media item has no videoCodec")
    # get video resolution
    try:
        info['video_resolution'] = item.videoResolution if item.videoResolution else 'Unknown'
    except AttributeError:
        log.debug("Media item has no videoResolution")
    # get video height
    try:
        info['video_height'] = item.height if item.height else 0
    except AttributeError:
        log.debug("Media item has no height")
    # get video width
    try:
        info['video_width'] = item.width if item.width else 0
    except AttributeError:
        log.debug("Media item has no width")
    # get video duration
    try:
        info['video_duration'] = item.duration if item.duration else 0
    except AttributeError:
        log.debug("Media item has no duration")
    # get audio codec
    try:
        info['audio_codec'] = item.audioCodec if item.audioCodec else 'Unknown'
    except AttributeError:
        log.debug("Media item has no audioCodec")
    # get audio channels
    try:
        for part in item.parts:
            for stream in part.audioStreams():
                if stream.channels:
                    log.debug(f"Added {stream.channels} channels for {stream.title if stream.title else 'Unknown'} audioStream")
                    info['audio_channels'] += stream.channels
        if info['audio_channels'] == 0:
            info['audio_channels'] = item.audioChannels if item.audioChannels else 0

    except AttributeError:
        log.debug("Media item has no audioChannels")

    # is this a multi part (cd1/cd2)
    if len(item.parts) > 1:
        info['multipart'] = True
    for part in item.parts:
        info['file'].append(part.file)
        info['file_size'] += part.size if part.size else 0
        if cfg['FIND_UNAVAILABLE'] and not part.exists:
            info['file_exists'] = False
        if cfg['FIND_EXTRA_TS']:
            name,ext = os.path.splitext(part.file)
            ext = ext.lower()
            if ext in info['file_exts']:
                info['file_exts'][ext] += 1
            else:
                info['file_exts'][ext] = 1

    return info


def delete_item(show_key, media_id):
    delete_url = urljoin(cfg['PLEX_SERVER'], '%s/media/%d' % (show_key, media_id))
    log.debug("Sending DELETE request to %r" % delete_url)
    if cfg['DRY_RUN']:
        print("\t\tDRY RUN -- Would've deleted media item: %r" % media_id)
    else:
        if requests.delete(delete_url, headers={'X-Plex-Token': cfg['PLEX_TOKEN']}).status_code == 200:
            print("✨ Successfully deleted 🆔%r" % media_id)

        else:
            print("⚠️ Deletion failed 🆔%r" % media_id)



############################################################
# MISC METHODS
############################################################

decision_filename = os.path.join(os.path.dirname(os.path.realpath(sys.argv[0])), 'decisions.log')


def write_decision(title=None, keeping=None, removed=None):
    lines = []
    if title:
        lines.append('\nTitle    : %s\n' % title)
    if keeping:
        lines.append('\tKeeping  : %r\n' % keeping)
    if removed:
        lines.append('\tRemoving : %r\n' % removed)

    with open(decision_filename, 'a') as fp:
        fp.writelines(lines)
    return


def should_skip(files):
    return any(skip_item in str(files_item) for files_item, skip_item in itertools.product(files, cfg['SKIP_LIST']))


def millis_to_string(millis):
    """ reference: https://stackoverflow.com/a/35990338 """
    try:
        seconds = (millis / 1000) % 60
        seconds = int(seconds)
        minutes = (millis / (1000 * 60)) % 60
        minutes = int(minutes)
        hours = (millis / (1000 * 60 * 60)) % 24
        return "%02d:%02d:%02d" % (hours, minutes, seconds)
    except Exception:
        log.exception(f"Exception occurred converting {millis} millis to readable string: ")
    return "%d milliseconds" % millis


def bytes_to_string(size_bytes):
    """
    reference: https://stackoverflow.com/a/6547474
    """
    try:
        if size_bytes == 1:
            return "1 byte"
        suffixes_table = [('bytes', 0), ('KB', 0), ('MB', 1), ('GB', 2), ('TB', 2), ('PB', 2)]

        num = float(size_bytes)
        for suffix, precision in suffixes_table:
            if num < 1024.0:
                break
            num /= 1024.0
        if precision == 0:
            formatted_size = "%d" % num
        else:
            formatted_size = str(round(num, ndigits=precision))
        return f"{formatted_size} {suffix}"
    except Exception:
        log.exception(f"Exception occurred converting {size_bytes} bytes to readable string: ")

    return "%d bytes" % size_bytes


def kbps_to_string(size_kbps):
    try:
        if size_kbps < 1024:
            return "%d Kbps" % size_kbps
        else:
            return "{:.2f} Mbps".format(size_kbps / 1024.)
    except Exception:
        log.exception(f"Exception occurred converting {size_kbps} Kbps to readable string: ")
    return "%d Bbps" % size_kbps


def build_tabulated(parts, items):
    headers = ['choice', 'score', 'id', 'file', 'size', 'duration', 'bitrate', 'resolution',
               'codecs']
    if cfg['FIND_DUPLICATE_FILEPATHS_ONLY']:
        headers.remove('score')

    part_data = []

    for choice, item_id in items.items():
        # add to part_data
        tmp = []
        for k in headers:
            if 'choice' in k:
                tmp.append(choice)
            elif 'score' in k:
                tmp.append(str(format(parts[item_id][k], ',d')))
            elif 'id' in k:
                tmp.append(parts[item_id][k])
            elif 'file' in k:
                tmp.append(parts[item_id][k])
            elif 'size' in k:
                tmp.append(bytes_to_string(parts[item_id]['file_size']))
            elif 'duration' in k:
                tmp.append(millis_to_string(parts[item_id]['video_duration']))
            elif 'bitrate' in k:
                tmp.append(kbps_to_string(parts[item_id]['video_bitrate']))
            elif 'resolution' in k:
                tmp.append("%s (%d x %d)" % (parts[item_id]['video_resolution'], parts[item_id]['video_width'],
                                             parts[item_id]['video_height']))
            elif 'codecs' in k:
                tmp.append("%s, %s x %d" % (parts[item_id]['video_codec'], parts[item_id]['audio_codec'],
                                            parts[item_id]['audio_channels']))
        part_data.append(tmp)
    return headers, part_data


############################################################
# MAIN
############################################################

if __name__ == "__main__":
    print("""
       _                 _                   __ _           _
 _ __ | | _____  __   __| |_   _ _ __   ___ / _(_)_ __   __| | ___ _ __
| '_ \| |/ _ \ \/ /  / _` | | | | '_ \ / _ \ |_| | '_ \ / _` |/ _ \ '__|
| |_) | |  __/>  <  | (_| | |_| | |_) |  __/  _| | | | | (_| |  __/ |
| .__/|_|\___/_/\_\  \__,_|\__,_| .__/ \___|_| |_|_| |_|\__,_|\___|_|
|_|                             |_|

#########################################################################
# Author:   l3uddz                                                      #
# URL:      https://github.com/l3uddz/plex_dupefinder                   #
# --                                                                    #
#         Part of the Cloudbox project: https://cloudbox.works          #
#########################################################################
#                   GNU General Public License v3.0                     #
#########################################################################
""")
    print("Initialized")
    # process arguments
    # Create argument parser
    parser = argparse.ArgumentParser(description='A python script that finds duplicate versions of media (TV episodes and movies) in your Plex Library and tells Plex to remove the lowest rated files/versions (based on user-specified scoring) to leave behind a single file/version.')
    # Add arguments
    parser.add_argument('--dry-run', action='store_true', help='Temporarily sets DRY_RUN')
    parser.add_argument('--skip-other-dupes', action='store_true', help='Temporarily sets SKIP_OTHER_DUPES')
    # Parse the arguments
    args = parser.parse_args()
    if args.dry_run:
        cfg['DRY_RUN'] = True
    if args.skip_other_dupes:
        cfg['SKIP_OTHER_DUPES'] = True
    process_later = {}
    # process sections
    print("Finding dupes...")
    for section in cfg['PLEX_LIBRARIES']:
        dupes = get_dupes(section)
        print("Found %d dupes for section %r" % (len(dupes), section))
        # loop returned duplicates
        for item in dupes:
            if item.type == 'episode':
                # Sometimes, item.index is None
                if item.index is None:
                    title = "%s - %s - %s" % (
                        item.grandparentTitle, item.seasonEpisode, item.title)
                else:
                    title = "%s - %02dx%02d - %s" % (
                        item.grandparentTitle, int(item.parentIndex), int(item.index), item.title)
            elif item.type == 'movie':
                title = item.title
            else:
                title = 'Unknown'

            log.info("Processing: %r", title)
            # If we're looking for unavailable media, double-check the existence and log the latest status to debug
            if cfg['FIND_UNAVAILABLE']:
                # If all files are already marked as available, log it and move on
                if all(part.exists for media in item.media for part in media.parts):
                    log.debug("All media is available for %s", item.title)
                # If any files are marked unavailable, tell Plex to recheck to verify
                else:
                    log.debug("Reloading %s", item.title)
                    item.reload(timeout=90) # Force a recheck if the media files exist
                media = parts = {}
                for media in item.media:
                    for part in media.parts:
                        log.debug("%r,%r -- %s exists = %s; size = %s", media.id, part.id, part.file, part.exists, part.size)
            # loop returned parts for media item (copy 1, copy 2...)
            parts = {}
            for part in item.media:
                part_info = get_media_info(part)
                # Skip media if it was automatically generated by Plex for optimization
                if part.isOptimizedVersion:
                    log.info("ID: %r (%r) -- Skipping optimized version", part.id, part_info['file'])
                    print("ID: %r (%r) -- Skipping optimized version" % (part.id, part_info['file']))
                    continue
                # Check if the path contains "\\Plex Versions\\" since isOptimizedVersion is sometimes not being set correctly
                elif cfg['SKIP_PLEX_VERSIONS_FOLDER'] and any("\\Plex Versions\\" in file_path for file_path in part_info['file']):
                    log.info("ID: %r (%r) -- Skipping Plex Versions; isOptimizedVersion = %r", part.id, part_info['file'], part.isOptimizedVersion)
                    print("ID: %r (%r) -- Skipping Plex Versions; isOptimizedVersion = %r" % (part.id, part_info['file'], part.isOptimizedVersion))
                    continue
                # Log all other instances in case troubleshooting is needed
                else:
                    log.debug("ID: %r (%r) -- Including; isOptimizedVersion = %r", part.id, part_info['file'], part.isOptimizedVersion)
                    # print("ID: %r (%r) -- Including; isOptimizedVersion = %r" % (part.id, part_info['file'], part.isOptimizedVersion))
                if not cfg['FIND_DUPLICATE_FILEPATHS_ONLY']:
                    part_info['score'] = get_score(part_info)
                part_info['show_key'] = item.key
                log.info("ID: %r - Score: %s - Meta:\n%r", part.id, part_info.get('score', 'N/A'),
                         part_info)
                parts[part.id] = part_info
            # If, after skipping media, we still have more than 1 file in the list, keep it on the list
            if len(parts) > 1:
                process_later[title] = parts
            # Skip this media if we don't have at least 2 files left in the list
            else:
                log.info("No duplicates after ignoring optimized versions for : %r", item.title)
                print("No duplicates after ignoring optimized versions for : %r" % item.title)

    # process processed items
    time.sleep(5)
    for item, parts in process_later.items():
        # Remove all unavailable media that are not in SKIP_LIST
        if cfg['FIND_UNAVAILABLE']:
            title_decided = False
            for media_id, part_info in parts.items():
                if not part_info['file_exists']:
                    if not title_decided:
                        title_decided = True
                        write_decision(title=item)
                    # Even if Plex is reporting the file as nonexistent, skip it if it has a file size.  Plex sometimes reports files as missing even though they are accessible by Plex.
                    if part_info['file_size'] > 0:
                        log.info("\tSkipping removal per file size (%r) : %r - %r", part_info['file_size'], media_id, part_info['file'])
                        print("\tSkipping removal per file size (%r) : %r - %r" % (part_info['file_size'], media_id, part_info['file']))
                        continue
                    if should_skip(part_info['file']):
                        log.info("\tSkipping removal per SKIP_LIST : %r - %r", media_id, part_info['file'])
                        print("\tSkipping removal per SKIP_LIST : %r - %r" % (media_id, part_info['file']))
                        continue
                    else:
                        log.info("Removing unavailable media : %r - %r (size: %r)", media_id, part_info['file'], part_info['file_size'])
                        print("Removing unavailable media : %r - %r (size: %r)" % (media_id, part_info['file'], part_info['file_size']))
                    delete_item(part_info['show_key'], media_id)
                    write_decision(removed=part_info)
                    time.sleep(2)

        # Delete .ts files when other media exists
        if cfg['FIND_EXTRA_TS']:
            title_decided = False
            file_exts = {}
            for media_id, part_info in parts.items():
                for k,v in part_info['file_exts'].items():
                    if k in file_exts:
                        file_exts[k] += v
                    else:
                        file_exts[k] = v
            if len(file_exts) > 1 and ".ts" in file_exts:
                for media_id, part_info in parts.items():
                    if ".ts" in part_info['file_exts']:
                        if len(part_info['file_exts']) == 1:
                            if not title_decided:
                                title_decided = True
                                write_decision(title=item)
                            if should_skip(part_info['file']):
                                log.info("\tSkipping removal per SKIP_LIST : %r - %r", media_id, part_info['file'])
                                print("\tSkipping removal per SKIP_LIST : %r - %r" % (media_id, part_info['file']))
                                continue
                            else:
                                log.info("Removing extra TS media : %r - %r", media_id, part_info['file'])
                                print("Removing extra TS media : %r - %r" % (media_id, part_info['file']))
                            delete_item(part_info['show_key'], media_id)
                            write_decision(removed=part_info)
                            time.sleep(2)
                        else:
                            # Not sure when this would happen, but let's note it.
                            print("\tSkipping removal of %r as there is more than one file type that make up %r for %s." % (part_info['file'], media_id, item))

        if not cfg['SKIP_OTHER_DUPES']:
            if not cfg['AUTO_DELETE']:
                partz = {}
                # manual delete
                print("\nWhich media item do you wish to keep for %r ?\n" % item)

                sort_key = None
                sort_order = None

                if cfg['FIND_DUPLICATE_FILEPATHS_ONLY']:
                    sort_key = "id"
                    sort_order_reverse = False
                else:
                    sort_key = "score"
                    sort_order_reverse = True

                media_items = {}
                best_item = None
                for pos, (media_id, part_info) in enumerate(collections.OrderedDict(
                        sorted(parts.items(), key=lambda x: x[1][sort_key], reverse=sort_order_reverse)).items(), start=1):
                    if pos == 1:
                        best_item = part_info
                    media_items[pos] = media_id
                    partz[media_id] = part_info

                headers, data = build_tabulated(partz, media_items)
                print(tabulate(data, headers=headers))

                keep_item = input("\nChoose item to keep (0 or s = skip | 1 or b = best): ")
                if (keep_item.lower() != 's') and (keep_item.lower() == 'b' or 0 < int(keep_item) <= len(media_items)):
                    write_decision(title=item)
                    for media_id, part_info in parts.items():
                        if keep_item.lower() == 'b' and best_item is not None and best_item == part_info:
                            print("\tKeeping  : %r" % media_id)
                            write_decision(keeping=part_info)
                        elif keep_item.lower() != 'b' and len(media_items) and media_id == media_items[int(keep_item)]:
                            print("\tKeeping  : %r" % media_id)
                            write_decision(keeping=part_info)
                        else:
                            print("\tRemoving : %r" % media_id)
                            delete_item(part_info['show_key'], media_id)
                            write_decision(removed=part_info)
                            time.sleep(2)
                elif keep_item.lower() == 's' or int(keep_item) == 0:
                    print("Skipping deletion(s) for %r" % item)
                else:
                    print("Unexpected response, skipping deletion(s) for %r" % item)
            else:
                # auto delete
                print("\nDetermining best media item to keep for %r ..." % item)
                #print("\n> %r" % item)
                keep_score = 0
                keep_id = None

                if cfg['FIND_DUPLICATE_FILEPATHS_ONLY']:
                    # select lowest id to keep
                    for media_id, part_info in parts.items():
                        if keep_score == 0 and keep_id is None:
                            keep_score = int(part_info['id'])
                            keep_id = media_id
                        elif int(part_info['id']) < keep_score:
                            keep_score = part_info['id']
                            keep_id = media_id
                else:
                    # select highest score to keep
                    for media_id, part_info in parts.items():
                        if int(part_info['score']) > keep_score:
                            keep_score = part_info['score']
                            keep_id = media_id

                if keep_id:
                    # delete other items
                    write_decision(title=item)
                    for media_id, part_info in parts.items():
                        formatedScore = '{:,}'.format(part_info['score'])
                        shortenedFilePath = '/' + '/'.join(part_info['file'][0].split('/')[-3:])
                        if media_id == keep_id:
                            print("✅%s🔺 %s 🆔%d" % (formatedScore, shortenedFilePath, media_id))
                            write_decision(keeping=part_info)
                        else:
                            print("\tRemoving : %r - %r" % (media_id, part_info['file']))
                            if should_skip(part_info['file']):
                                print("☑️%s🔺 %s 🆔%d" % (formatedScore, shortenedFilePath, media_id))
                            else:
                                print("❌%s🔺 %s 🆔%d" % (formatedScore, shortenedFilePath, media_id))
                                delete_item(part_info['show_key'], media_id)
                                write_decision(removed=part_info)
                                time.sleep(2)
                else:
                    print("Unable to determine best media item to keep for %r", item)
