from flask import Flask, request, jsonify, send_file, after_this_request
from flask_cors import CORS
import libtorrent as lt
import os
import json
import random
import shutil
import threading

app = Flask(__name__)
CORS(app, origins="*", methods=["GET", "POST"])

downloads = []
downloading = []


def remove_file_later(file_path, delay=10):
    """
    Removes the file at the given path after the given delay in seconds
    """
    def remove_file():
        if os.path.exists(file_path):
            os.remove(file_path)
    threading.Timer(delay, remove_file).start()


class TorrentDownload:
    """
    A class to represent a torrent download
    """

    def __init__(self, torrent_path):
        self.torrent_path = torrent_path
        self.handle = None
        self.session = lt.session({'listen_interfaces': '0.0.0.0:6881'})
        self.stopped = False

    def start(self):
        """
        Start the torrent download
        """
        info = lt.torrent_info(self.torrent_path)
        params = {'ti': info, 'save_path': '.'}
        self.handle = self.session.add_torrent(params)

    def stop(self):
        """
        Stop the torrent download permanently
        """
        self.stopped = True
        if self.handle:
            self.session.remove_torrent(self.handle)

    @property
    def progress(self):
        """
        Returns the progress of the download in percent (0-100)
        """
        if self.handle:
            return self.handle.status().progress * 100
        return None

    @property
    def status(self):
        """
        Returns the full status of the download
        """
        if self.handle:
            return self.handle.status()


def isClass(obj):
    """
    Returns if the object belongs to a non-standard class
    Standart classes are classes that are not defined in the __main__ module like int, str, list, etc.
    """

    standart_classes = [int, str, list, dict, tuple, set, frozenset,
                        bool, float, complex, bytes, bytearray, memoryview, type(None)]
    return type(obj) not in standart_classes


def beautifyStatus(status, index):
    """
    Converts the status object to a dictionary of useful information
    """
    attr = dir(status)
    ret = {}
    handle = downloads[index].handle
    for i in attr:
        if not i.startswith('_'):
            value = getattr(status, i)
            try:
                if (isClass(value)):
                    raise TypeError
                # Try to serialize the value to JSON
                json.dumps(value)
                ret[i] = value
            except TypeError:
                # If the value is not serializable, convert it to a string
                ret[i] = str(value)

    is_paused = not downloading[index]
    json.dumps(is_paused)
    ret["is_paused"] = is_paused

    download_limit = handle.download_limit()
    upload_limit = handle.upload_limit()
    json.dumps(download_limit)
    json.dumps(upload_limit)
    ret["download_limit"] = download_limit
    ret["upload_limit"] = upload_limit

    return ret


def makeProgressBar(percent, width=30):
    """
    Returns a progress bar of the given width and percent for printing in the terminal
    """
    return ('█' * int(percent * width / 100)).ljust(width, '░')


def printify(lst, spaces=4):
    """
    Returns a string of the list with spaces between each element
    """
    return (spaces * ' ').join([str(i) for i in lst])


@ app.route('/add_torrent', methods=['POST'])
def add_torrent():
    #  return "Test"
    # print info about the request
    if 'file' not in request.files:
        return 'No file uploaded', 400
    file = request.files['file']
    if file.filename == '':
        return 'No file selected', 400

    file_path = os.path.join(os.path.dirname(__file__), file.filename)
    file.save(file_path)

    if True:
        download_obj = TorrentDownload(file_path)
        download_obj.start()
        downloads.append(download_obj)
        downloading.append(True)
        return f'Torrent "{download_obj.status.name}" added successfully!', 201
    else:
        return "Wow no error", 200


@ app.route('/list_torrents', methods=['GET'])
def list_torrents():
    return jsonify([download.status.name for download in downloads]), 200


@ app.route('/get_torrent_status_string/<int:index>', methods=['GET'])
def get_torrent_status(index):
    if index < 0 or index >= len(downloads):
        return 'Invalid index', 400

    download_obj = downloads[index]
    status = download_obj.status

    if status is None:
        return 'Torrent not found', 404

    lst = [str(round(status.progress * 10000) / 100) + "%",
           makeProgressBar(status.progress * 100),
           str(round(status.download_rate / 1024 / 1024 * 10) / 10) + " MB/s ↓",
           str(round(status.upload_rate / 1024 / 1024 * 10) / 10) + " MB/s ↑",
           str(status.num_peers) + " peers",
           status.state,
           downloading[index]]
    return printify(lst), 200


@ app.route('/get_torrent_status/<int:index>', methods=['GET'])
def get_torrent_status_json(index):
    if index < 0 or index >= len(downloads):
        return 'Invalid index', 400

    download_obj = downloads[index]
    status = download_obj.status

    if status is None:
        return 'Torrent not found', 404
    return jsonify(beautifyStatus(status, index)), 200


@ app.route('/stop_torrent/<int:index>', methods=['GET'])
def stop_torrent(index):
    if index < 0 or index >= len(downloads):
        return 'Invalid index', 400
    downloading[index] = False
    download_obj = downloads[index]
    info = download_obj.handle.get_torrent_info()
    filenames = []
    for i in range(info.num_files()):
        file = info.file_at(i)
        filenames.append(file.path)
        if os.path.exists(file.path):
            os.remove(file.path)
    try:
        parent_dir = os.path.dirname(filenames[0])
        shutil.rmtree(parent_dir)
    except:
        pass

    #  delete from list
    download_obj.stop()
    del downloads[index]
    del downloading[index]
    return 'Torrent stopped', 200


@ app.route('/get_torrent_files/<int:index>', methods=['GET'])
def get_torrent_files(index):
    if index < 0 or index >= len(downloads):
        return 'Invalid index', 400

    download_obj = downloads[index]
    info = download_obj.handle.get_torrent_info()

    lst = []

    for i in range(info.num_files()):
        file = info.file_at(i)
        lst.append({
            'name': file.path,
            'size': file.size,
            'progress': download_obj.handle.file_progress(i),
            'priority': download_obj.handle.file_priority(i)
        })
    return jsonify(lst), 200


@ app.route('/pause_torrent/<int:index>', methods=['GET'])
def pause_torrent(index):
    if index < 0 or index >= len(downloads):
        return 'Invalid index', 400

    download_obj = downloads[index]
    download_obj.session.pause()
    download_obj.session.is_paused = True
    downloading[index] = False
    return 'Torrent paused', 200


@ app.route('/resume_torrent/<int:index>', methods=['GET'])
def resume_torrent(index):
    if index < 0 or index >= len(downloads):
        return 'Invalid index', 400

    download_obj = downloads[index]
    download_obj.session.resume()
    download_obj.session.is_paused = False
    downloading[index] = True
    return 'Torrent resumed', 200


@ app.route('/get_torrent_file/<int:index>/<int:file_index>', methods=['GET'])
def get_torrent_file(index, file_index):
    if index < 0 or index >= len(downloads):
        return 'Invalid index', 400

    download_obj = downloads[index]
    info = download_obj.handle.get_torrent_info()
    if file_index < 0 or file_index >= info.num_files():
        return 'Invalid file index', 400
    file = info.file_at(file_index)
    return send_file(file.path, as_attachment=True, download_name=file.path.split('/')[-1])


@ app.route('/get_torrent_file_stream/<int:index>/<int:file_index>', methods=['GET'])
def get_torrent_file_stream(index, file_index):
    if index < 0 or index >= len(downloads):
        return 'Invalid index', 400

    download_obj = downloads[index]
    info = download_obj.handle.get_torrent_info()
    if file_index < 0 or file_index >= info.num_files():
        return 'Invalid file index', 400
    file = info.file_at(file_index)
    return send_file(file.path, as_attachment=False, download_name=file.path.split('/')[-1])


@ app.route('/get_all_files/<int:index>', methods=['GET'])
def get_all_files(index):
    if index < 0 or index >= len(downloads):
        return 'Invalid index', 400

    download_obj = downloads[index]
    name = download_obj.status.name
    try:
        shutil.make_archive(name, 'zip', name)
    except Exception as error:
        return "The torrent might be a single file torrent, try downloading it directly", 400

    @after_this_request
    def remove_file(response):
        try:
            remove_file_later(name + '.zip', 60)
        except Exception as error:
            pass
        return response

    return send_file(name + '.zip', as_attachment=True, download_name=name + '.zip')


@app.route('/set_download_speed/<int:index>/<int:speed>', methods=['GET'])
def set_download_speed(index, speed):
    if index < 0 or index >= len(downloads):
        return 'Invalid index', 400

    download_obj = downloads[index]
    if (speed == 0):
        download_obj.handle.set_download_limit(-1)
    else:
        download_obj.handle.set_download_limit(speed)
    #  print new limit
    print(download_obj.handle.download_limit())
    return 'Download speed set', 200


@app.route('/set_upload_speed/<int:index>/<int:speed>', methods=['GET'])
def set_upload_speed(index, speed):
    if index < 0 or index >= len(downloads):
        return 'Invalid index', 400

    download_obj = downloads[index]
    if (speed == 0):
        download_obj.handle.set_upload_limit(-1)
    else:
        download_obj.handle.set_upload_limit(speed)
    return 'Upload speed set', 200


@app.route('/', methods=['GET'])
def index():
    return "Hey this is working!"


if __name__ == '__main__':
    app.run(debug=True, use_reloader=False)
