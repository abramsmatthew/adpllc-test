from docassemble.webapp.app_object import app
from docassemble.webapp.db_object import db
from docassemble.base.config import daconfig, s3_config, S3_ENABLED, gc_config, GC_ENABLED, dbtableprefix, hostname, in_celery
from docassemble.webapp.files import SavedFile, get_ext_and_mimetype
from docassemble.webapp.core.models import Uploads
from docassemble.base.logger import logmessage
from docassemble.webapp.users.models import UserModel, ChatLog, UserDict, UserDictKeys
from docassemble.webapp.core.models import Attachments, Uploads, SpeakList, ObjectStorage
from docassemble.base.generate_key import random_string
from sqlalchemy import or_, and_
import docassemble.webapp.database
import logging
import urllib
import tempfile
import cPickle as pickle
import codecs
#import string
#import random
import pprint
import datetime
import json
import types
from Crypto.Cipher import AES
from Crypto import Random
from dateutil import tz
import tzlocal

import docassemble.base.parse
import re
import os
import sys
import pyPdf
from flask import session, current_app, has_request_context, url_for
from flask_mail import Mail, Message
from flask_wtf.csrf import generate_csrf
from PIL import Image
import xml.etree.ElementTree as ET
import docassemble.webapp.worker
#sys.stderr.write("I am in backend\n")

import docassemble.webapp.setup

DEBUG = daconfig.get('debug', False)
docassemble.base.parse.debug = DEBUG

def write_record(key, data):
    new_record = ObjectStorage(key=key, value=pack_object(data))
    db.session.add(new_record)
    db.session.commit()
    return new_record.id

def read_records(key):
    logmessage("got here!")
    results = dict()
    for record in ObjectStorage.query.filter_by(key=key).order_by(ObjectStorage.id):
        logmessage("and here!")
        results[record.id] = unpack_object(record.value)
    return results

def delete_record(key, id):
    ObjectStorage.query.filter_by(key=key, id=id).delete()
    db.session.commit()

def save_numbered_file(filename, orig_path, yaml_file_name=None, uid=None):
    if uid is None:
        if has_request_context():
            uid = session['uid']
        else:
            uid = docassemble.base.functions.get_uid()
    file_number = get_new_file_number(uid, filename, yaml_file_name=yaml_file_name)
    extension, mimetype = get_ext_and_mimetype(filename)
    new_file = SavedFile(file_number, extension=extension, fix=True)
    new_file.copy_from(orig_path)
    new_file.save(finalize=True)
    return(file_number, extension, mimetype)

def savedfile_numbered_file(filename, orig_path, yaml_file_name=None, uid=None):
    if uid is None:
        if has_request_context():
            uid = session['uid']
        else:
            uid = docassemble.base.functions.get_uid()
    file_number = get_new_file_number(uid, filename, yaml_file_name=yaml_file_name)
    extension, mimetype = get_ext_and_mimetype(filename)
    new_file = SavedFile(file_number, extension=extension, fix=True)
    new_file.copy_from(orig_path)
    new_file.save(finalize=True)
    return new_file

def absolute_filename(the_file):
    match = re.match(r'^docassemble.playground([0-9]+):(.*)', the_file)
    #logmessage("absolute_filename call: " + the_file)
    if match:
        filename = re.sub(r'[^A-Za-z0-9\-\_\.]', '', match.group(2))
        #logmessage("absolute_filename: filename is " + filename)
        playground = SavedFile(match.group(1), section='playground', fix=True, filename=filename)
        return playground
    match = re.match(r'^/playgroundtemplate/([0-9]+)/(.*)', the_file)
    if match:
        filename = re.sub(r'[^A-Za-z0-9\-\_\.]', '', match.group(2))
        playground = SavedFile(match.group(1), section='playgroundtemplate', fix=True, filename=filename)
        return playground
    match = re.match(r'^/playgroundstatic/([0-9]+)/(.*)', the_file)
    if match:
        filename = re.sub(r'[^A-Za-z0-9\-\_\.]', '', match.group(2))
        playground = SavedFile(match.group(1), section='playgroundstatic', fix=True, filename=filename)
        return playground
    match = re.match(r'^/playgroundsources/([0-9]+)/(.*)', the_file)
    if match:
        filename = re.sub(r'[^A-Za-z0-9\-\_\.]', '', match.group(2))
        playground = SavedFile(match.group(1), section='playgroundsources', fix=True, filename=filename)
        return playground
    return(None)

def get_info_from_file_reference(file_reference, **kwargs):
    #sys.stderr.write('file reference is ' + str(file_reference) + "\n")
    #logmessage('file reference is ' + str(file_reference))
    if 'convert' in kwargs:
        convert = kwargs['convert']
    else:
        convert = None
    if re.match('[0-9]+', str(file_reference)):
        result = get_info_from_file_number(int(file_reference))
    elif re.search(r'^https*://', str(file_reference)):
        #logmessage(str(file_reference) + " is a URL")
        m = re.search('(\.[A-Za-z0-9]+)$', file_reference)
        if m:
            suffix = m.group(1)
        else:
            suffix = '.html'
        result = dict(tempfile=tempfile.NamedTemporaryFile(suffix=suffix))
        urllib.urlretrieve(file_reference, result['tempfile'].name)
        result['fullpath'] = result['tempfile'].name
        #logmessage("Downloaded to " + result['tempfile'].name)
    else:
        #logmessage(str(file_reference) + " is not a URL")
        result = dict()
        question = kwargs.get('question', None)
        the_package = None
        parts = file_reference.split(':')
        if len(parts) == 1:
            the_package = None
            if question is not None:
                the_package = question.from_source.package
            if the_package is not None:
                file_reference = the_package + ':' + file_reference
            else:
                file_reference = 'docassemble.base:' + file_reference
        result['fullpath'] = docassemble.base.functions.static_filename_path(file_reference)
    #logmessage("path is " + str(result['fullpath']))
    if result['fullpath'] is not None and os.path.isfile(result['fullpath']):
        result['filename'] = os.path.basename(result['fullpath'])
        ext_type, result['mimetype'] = get_ext_and_mimetype(result['fullpath'])
        path_parts = os.path.splitext(result['fullpath'])
        result['path'] = path_parts[0]
        result['extension'] = path_parts[1].lower()
        result['extension'] = re.sub(r'\.', '', result['extension'])
        #logmessage("Extension is " + result['extension'])
        if convert is not None and result['extension'] in convert:
            #logmessage("Converting...")
            if os.path.isfile(result['path'] + '.' + convert[result['extension']]):
                #logmessage("Found conversion file ")
                result['extension'] = convert[result['extension']]
                result['fullpath'] = result['path'] + '.' + result['extension']
                ext_type, result['mimetype'] = get_ext_and_mimetype(result['fullpath'])
            else:
                logmessage("Did not find file " + result['path'] + '.' + convert[result['extension']])
                return dict()
        #logmessage("Full path is " + result['fullpath'])
        if os.path.isfile(result['fullpath']):
            add_info_about_file(result['fullpath'], result)
    else:
        logmessage("File reference " + str(file_reference) + " DID NOT EXIST.")
    return(result)

#docassemble.base.parse.set_file_finder(get_info_from_file_reference)

mail = Mail(app)

def da_send_mail(the_message):
    mail.send(the_message)

#docassemble.base.parse.set_da_send_mail(da_send_mail)

#docassemble.base.parse.set_save_numbered_file(save_numbered_file)

import docassemble.webapp.machinelearning
import docassemble.base.functions
from docassemble.base.functions import dict_as_json
DEFAULT_LANGUAGE = daconfig.get('language', 'en')
DEFAULT_LOCALE = daconfig.get('locale', 'en_US.utf8')
DEFAULT_DIALECT = daconfig.get('dialect', 'us')
if 'timezone' in daconfig and daconfig['timezone'] is not None:
    DEFAULT_TIMEZONE = daconfig['timezone']
else:
    try:
        DEFAULT_TIMEZONE = tzlocal.get_localzone().zone
    except:
        DEFAULT_TIMEZONE = 'America/New_York'

docassemble.base.functions.update_server(default_language=DEFAULT_LANGUAGE,
                                         default_locale=DEFAULT_LOCALE,
                                         default_dialect=DEFAULT_DIALECT,
                                         default_timezone=DEFAULT_TIMEZONE,
                                         default_country=daconfig.get('country', re.sub(r'\..*', r'', DEFAULT_LOCALE)),
                                         daconfig=daconfig,
                                         debug_status=DEBUG,
                                         save_numbered_file=save_numbered_file,
                                         send_mail=da_send_mail,
                                         absolute_filename=absolute_filename,
                                         write_record=write_record,
                                         read_records=read_records,
                                         delete_record=delete_record,
                                         generate_csrf=generate_csrf,
                                         url_for=url_for,
                                         file_finder=get_info_from_file_reference)
docassemble.base.functions.set_language(DEFAULT_LANGUAGE, dialect=DEFAULT_DIALECT)
docassemble.base.functions.set_locale(DEFAULT_LOCALE)
docassemble.base.functions.update_locale()
if 'currency symbol' in daconfig:
    docassemble.base.functions.update_language_function('*', 'currency_symbol', lambda: daconfig['currency symbol'])

if S3_ENABLED:
    import docassemble.webapp.amazon
    s3 = docassemble.webapp.amazon.s3object(s3_config)
else:
    s3 = None

initial_dict = dict(_internal=dict(progress=0, tracker=0, steps_offset=0, secret=None, informed=dict(), livehelp=dict(availability='unavailable', mode='help', roles=list(), partner_roles=list()), answered=set(), answers=dict(), objselections=dict(), starttime=None, modtime=None, accesstime=dict(), tasks=dict(), gather=list()), url_args=dict())
#else:
#    initial_dict = dict(_internal=dict(tracker=0, steps_offset=0, answered=set(), answers=dict(), objselections=dict()), url_args=dict())
if 'initial_dict' in daconfig:
    initial_dict.update(daconfig['initial_dict'])
docassemble.base.parse.set_initial_dict(initial_dict)
from docassemble.base.functions import pickleable_objects

# def absolute_validator(the_file):
#     #logmessage("Running my validator")
#     if the_file.startswith(os.path.join(UPLOAD_DIRECTORY, 'playground')) and current_user.is_authenticated and not current_user.is_anonymous and current_user.has_role('admin', 'developer') and os.path.dirname(the_file) == os.path.join(UPLOAD_DIRECTORY, 'playground', str(current_user.id)):
#         return True
#     return False

#docassemble.base.parse.set_absolute_filename(absolute_filename)
#logmessage("Server started")

def can_access_file_number(file_number, uid=None):
    if uid is None:
        if has_request_context():
            uid = session['uid']
        else:
            uid = docassemble.base.functions.get_uid()
    upload = Uploads.query.filter_by(indexno=file_number, key=uid).first()
    if upload:
        return True
    return False

def get_new_file_number(user_code, file_name, yaml_file_name=None):
    new_upload = Uploads(key=user_code, filename=file_name, yamlfile=yaml_file_name)
    db.session.add(new_upload)
    db.session.commit()
    return new_upload.indexno
    # indexno = None
    # cur = conn.cursor()
    # cur.execute("INSERT INTO uploads (key, filename) values (%s, %s) RETURNING indexno", [user_code, file_name])
    # for d in cur:
    #     indexno = d[0]
    # conn.commit()
    # return (indexno)

def get_info_from_file_number(file_number, privileged=False):
    if has_request_context():
        uid = session['uid']
    else:
        uid = docassemble.base.functions.get_uid()
    result = dict()
    if privileged:
        upload = Uploads.query.filter_by(indexno=file_number).first()
    else:
        upload = Uploads.query.filter_by(indexno=file_number, key=uid).first()
    if upload:
        result['filename'] = upload.filename
        result['extension'], result['mimetype'] = get_ext_and_mimetype(result['filename'])
        result['savedfile'] = SavedFile(file_number, extension=result['extension'], fix=True)
        result['path'] = result['savedfile'].path
        result['fullpath'] = result['path'] + '.' + result['extension']
    if 'path' not in result:
        logmessage("path is not in result for " + str(file_number))
        return result
    filename = result['path'] + '.' + result['extension']
    if os.path.isfile(filename):
        add_info_about_file(filename, result)
    else:
        logmessage("Filename DID NOT EXIST.")
    return(result)

def add_info_about_file(filename, result):
    if result['extension'] == 'pdf':
        reader = pyPdf.PdfFileReader(open(filename))
        result['pages'] = reader.getNumPages()
    elif result['extension'] in ['png', 'jpg', 'gif']:
        im = Image.open(filename)
        result['width'], result['height'] = im.size
    elif result['extension'] == 'svg':
        tree = ET.parse(filename)
        root = tree.getroot()
        viewBox = root.attrib.get('viewBox', None)
        if viewBox is not None:
            dimen = viewBox.split(' ')
            if len(dimen) == 4:
                result['width'] = float(dimen[2]) - float(dimen[0])
                result['height'] = float(dimen[3]) - float(dimen[1])
    return

if in_celery:
    LOGFILE = daconfig.get('celery_flask_log', '/tmp/celery-flask.log')
else:
    LOGFILE = daconfig.get('flask_log', '/tmp/flask.log')

if not os.path.exists(LOGFILE):
    with open(LOGFILE, 'a'):
        os.utime(LOGFILE, None)

error_file_handler = logging.FileHandler(filename=LOGFILE)
error_file_handler.setLevel(logging.DEBUG)
app.logger.addHandler(error_file_handler)

#sys.stderr.write("__name__ is " + str(__name__) + " and __package__ is " + str(__package__) + "\n")

def flask_logger(message):
    #app.logger.warning(message)
    sys.stderr.write(unicode(message) + "\n")
    return

def pad(the_string):
    return the_string + (16 - len(the_string) % 16) * chr(16 - len(the_string) % 16)

def unpad(the_string):
    return the_string[0:-ord(the_string[-1])]

def encrypt_phrase(phrase, secret):
    iv = current_app.secret_key[:16]
    encrypter = AES.new(secret, AES.MODE_CBC, iv)
    return iv + codecs.encode(encrypter.encrypt(pad(phrase)), 'base64').decode()

def pack_phrase(phrase):
    return codecs.encode(phrase, 'base64').decode()

def decrypt_phrase(phrase_string, secret):
    decrypter = AES.new(secret, AES.MODE_CBC, str(phrase_string[:16]))
    return unpad(decrypter.decrypt(codecs.decode(phrase_string[16:], 'base64')))

def unpack_phrase(phrase_string):
    return codecs.decode(phrase_string, 'base64')

def encrypt_dictionary(the_dict, secret):
    #sys.stderr.write("40\n")
    iv = random_string(16)
    #iv = Random.new().read(AES.block_size)
    #sys.stderr.write("41\n")
    #sys.stderr.write("iv is " + str(iv) + "\n")
    #sys.stderr.write("block size is " + str(AES.block_size) + "\n")
    #sys.stderr.write("secret is " + str(repr(secret)) + "\n")
    encrypter = AES.new(secret, AES.MODE_CBC, iv)
    #sys.stderr.write("42\n")
    #one = pickleable_objects(the_dict)
    #sys.stderr.write("43\n")
    #two = pickle.dumps(one)
    #sys.stderr.write("44\n")
    #three = pad(two)
    #sys.stderr.write("45\n")
    #four = encrypter.encrypt(three)
    #sys.stderr.write("46\n")
    #logmessage(pprint.pformat(pickleable_objects(the_dict)))
    return iv + codecs.encode(encrypter.encrypt(pad(pickle.dumps(pickleable_objects(the_dict)))), 'base64').decode()

def pack_object(the_object):
    return codecs.encode(pickle.dumps(safe_pickle(the_object)), 'base64').decode()

def unpack_object(the_string):
    return pickle.loads(codecs.decode(the_string, 'base64'))

def safe_pickle(the_object):
    if type(the_object) is list:
        return [safe_pickle(x) for x in the_object]
    if type(the_object) is dict:
        new_dict = dict()
        for key, value in the_object.iteritems():
            new_dict[key] = safe_pickle(value)
        return new_dict
    if type(the_object) is set:
        new_set = set()
        for sub_object in the_object:
            new_set.add(safe_pickle(sub_object))
        return new_set
    if type(the_object) in [types.ModuleType, types.FunctionType, types.TypeType, types.BuiltinFunctionType, types.BuiltinMethodType, types.MethodType, types.ClassType]:
        return None
    return the_object

def pack_dictionary(the_dict):
    # sys.stderr.write("pack_dictionary keys:\n")
    # for key in pickleable_objects(the_dict):
    #     sys.stderr.write("  " + key + ": " + pprint.pformat(the_dict[key]) + "\n")
    return codecs.encode(pickle.dumps(pickleable_objects(the_dict)), 'base64').decode()

def decrypt_dictionary(dict_string, secret):
    #sys.stderr.write("60\n")
    #sys.stderr.write("secret is " + str(repr(secret)) + "\n")
    decrypter = AES.new(secret, AES.MODE_CBC, str(dict_string[:16]))
    #sys.stderr.write("61\n")
    #one = codecs.decode(dict_string[16:], 'base64')
    #sys.stderr.write("62\n")
    #two = decrypter.decrypt(one)
    #sys.stderr.write("63\n")
    #three = unpad(two)
    #sys.stderr.write("64\n")
    #four = pickle.loads(three)
    #sys.stderr.write(pprint.pformat(four, depth=4, indent=4) + "\n")
    #sys.stderr.write(json.dumps(four) + "\n")
    #sys.stderr.write("65\n")
    #return four
    return pickle.loads(unpad(decrypter.decrypt(codecs.decode(dict_string[16:], 'base64'))))

def unpack_dictionary(dict_string):
    return pickle.loads(codecs.decode(dict_string, 'base64'))

def nice_date_from_utc(timestamp, timezone=tz.tzlocal()):
    return timestamp.replace(tzinfo=tz.tzutc()).astimezone(timezone).strftime('%x %X')

def nice_utc_date(timestamp, timezone=tz.tzlocal()):
    return timestamp.strftime('%F %T')

def fetch_user_dict(user_code, filename, secret=None):
    user_dict = None
    steps = 0
    encrypted = True
    #sys.stderr.write("50\n")
    subq = db.session.query(db.func.max(UserDict.indexno).label('indexno'), db.func.count(UserDict.indexno).label('count')).filter(UserDict.key == user_code and UserDict.filename == filename).subquery()
    #sys.stderr.write("51\n")
    results = db.session.query(UserDict.dictionary, UserDict.encrypted, subq.c.count).join(subq, subq.c.indexno == UserDict.indexno)
    for d in results:
        #sys.stderr.write("51.1\n")
        if d.dictionary:
            if d.encrypted:
                #sys.stderr.write("52\n")
                user_dict = decrypt_dictionary(d.dictionary, secret)
                #sys.stderr.write("53\n")
            else:
                #sys.stderr.write("54\n")
                user_dict = unpack_dictionary(d.dictionary)
                encrypted = False
        if d.count:
            steps = d.count
        #sys.stderr.write("55\n")
        break
    #sys.stderr.write("56\n")
    return steps, user_dict, encrypted

def fetch_previous_user_dict(user_code, filename, secret):
    user_dict = None
    max_indexno = db.session.query(db.func.max(UserDict.indexno)).filter(UserDict.key == user_code and UserDict.filename == filename).scalar()
    if max_indexno is not None:
        UserDict.query.filter_by(indexno=max_indexno).delete()
        db.session.commit()
    return fetch_user_dict(user_code, filename, secret=secret)

def advance_progress(user_dict):
    user_dict['_internal']['progress'] += 0.05*(100-user_dict['_internal']['progress'])
    return

def reset_user_dict(user_code, filename):
    UserDict.query.filter_by(key=user_code, filename=filename).delete()
    db.session.commit()
    UserDictKeys.query.filter_by(key=user_code, filename=filename).delete()
    db.session.commit()
    for upload in Uploads.query.filter_by(key=user_code, yamlfile=filename).all():
        old_file = SavedFile(upload.indexno)
        old_file.delete()
    Uploads.query.filter_by(key=user_code, yamlfile=filename).delete()
    db.session.commit()
    Attachments.query.filter_by(key=user_code, filename=filename).delete()
    db.session.commit()
    SpeakList.query.filter_by(key=user_code, filename=filename).delete()
    db.session.commit()
    ChatLog.query.filter_by(key=user_code, filename=filename).delete()
    db.session.commit()
    return

def get_person(user_id, cache):
    if user_id in cache:
        return cache[user_id]
    for record in UserModel.query.filter_by(id=user_id):
        cache[record.id] = record
        return record
    return None

def get_chat_log(chat_mode, yaml_filename, session_id, user_id, temp_user_id, secret, self_user_id, self_temp_id):
    messages = list()
    people = dict()
    if user_id is not None:
        if get_person(user_id, people) is None:
            return list()
        chat_person_type = 'auth'
        chat_person_id = user_id
    else:
        chat_person_type = 'anon'
        chat_person_id = temp_user_id
    if self_user_id is not None:
        if get_person(self_user_id, people) is None:
            return list()
        self_person_type = 'auth'
        self_person_id = self_user_id
    else:
        self_person_type = 'anon'
        self_person_id = self_temp_id
    if chat_mode in ['peer', 'peerhelp']:
        open_to_peer = True
    else:
        open_to_peer = False
    if chat_person_type == 'auth':
        if chat_mode in ['peer', 'peerhelp']:
            records = ChatLog.query.filter(and_(ChatLog.filename == yaml_filename, ChatLog.key == session_id, or_(ChatLog.open_to_peer == True, ChatLog.owner_id == chat_person_id))).order_by(ChatLog.id).all()
        else:
            records = ChatLog.query.filter(and_(ChatLog.filename == yaml_filename, ChatLog.key == session_id, ChatLog.owner_id == chat_person_id)).order_by(ChatLog.id).all()
        for record in records:
            if record.encrypted:
                try:
                    message = decrypt_phrase(record.message, secret)
                except:
                    sys.stderr.write("Could not decrypt phrase with secret " + secret + "\n")
                    continue
            else:
                message = unpack_phrase(record.message)
            modtime = nice_utc_date(record.modtime)
            if self_person_type == 'auth':
                if self_person_id == record.user_id:
                    is_self = True
                else:
                    is_self = False
            else:
                if self_person_id == record.temp_user_id:
                    is_self = True
                else:
                    is_self = False
            if record.user_id is not None:
                person = get_person(record.user_id, people)
                if person is None:
                    sys.stderr.write("Person " + str(record.user_id) + " did not exist\n")
                    continue
                messages.append(dict(id=record.id, is_self=is_self, temp_owner_id=record.temp_owner_id, temp_user_id=record.temp_user_id, owner_id=record.owner_id, user_id=record.user_id, first_name=person.first_name, last_name=person.last_name, email=person.email, modtime=modtime, message=message, roles=[role.name for role in person.roles]))
            else:
                messages.append(dict(id=record.id, is_self=is_self, temp_owner_id=record.temp_owner_id, temp_user_id=record.temp_user_id, owner_id=record.owner_id, user_id=record.user_id, modtime=modtime, message=message, roles=['user']))
    else:
        if chat_mode in ['peer', 'peerhelp']:
            records = ChatLog.query.filter(and_(ChatLog.filename == yaml_filename, ChatLog.key == session_id, or_(ChatLog.open_to_peer == True, ChatLog.temp_owner_id == chat_person_id))).order_by(ChatLog.id).all()
        else:
            records = ChatLog.query.filter(and_(ChatLog.filename == yaml_filename, ChatLog.key == session_id, ChatLog.temp_owner_id == chat_person_id)).order_by(ChatLog.id).all()
        for record in records:
            if record.encrypted:
                try:
                    message = decrypt_phrase(record.message, secret)
                except:
                    sys.stderr.write("Could not decrypt phrase with secret " + secret + "\n")
                    continue
            else:
                message = unpack_phrase(record.message)
            modtime = nice_utc_date(record.modtime)
            if self_person_type == 'auth':
                if self_person_id == record.user_id:
                    is_self = True
                else:
                    is_self = False
            else:
                #logmessage("self person id is " + str(self_person_id) + " and record user id is " + str(record.temp_user_id))
                if self_person_id == record.temp_user_id:
                    is_self = True
                else:
                    is_self = False
            if record.user_id is not None:
                person = get_person(record.user_id, people)
                if person is None:
                    sys.stderr.write("Person " + str(record.user_id) + " did not exist\n")
                    continue
                messages.append(dict(id=record.id, is_self=is_self, temp_owner_id=record.temp_owner_id, temp_user_id=record.temp_user_id, owner_id=record.owner_id, user_id=record.user_id, first_name=person.first_name, last_name=person.last_name, email=person.email, modtime=modtime, message=message, roles=[role.name for role in person.roles]))
            else:
                messages.append(dict(id=record.id, is_self=is_self, temp_owner_id=record.temp_owner_id, temp_user_id=record.temp_user_id, owner_id=record.owner_id, user_id=record.user_id, modtime=modtime, message=message, roles=['user']))
    return messages
