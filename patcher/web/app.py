import flask
import traceback
import sys
import os
import time
import io
import zipfile
import hashlib
from flask import request
sys.path.append('..')
from patcher import FirmwarePatcher

app = flask.Flask(__name__)


@app.errorhandler(Exception)
def handle_bad_request(e):
    return 'Exception occured:\n{}'.format(traceback.format_exc()), \
            400, {'Content-Type': 'text/plain'}

# http://flask.pocoo.org/snippets/40/
@app.context_processor
def override_url_for():
    return dict(url_for=dated_url_for)

def dated_url_for(endpoint, **values):
    if endpoint == 'static':
        filename = values.get('filename', None)
        if filename:
            file_path = os.path.join(app.root_path,
                                     endpoint, filename)
            values['q'] = int(os.stat(file_path).st_mtime)
    return flask.url_for(endpoint, **values)

@app.route('/cfw')
def patch_firmware():
    version = flask.request.args.get('version', None)
    if version not in ['DRV126']:
        return 'Invalid firmware version.', 400

    with open('bins/{}.bin'.format(version), 'rb') as fp:
        patcher = FirmwarePatcher(fp.read())

    if ((flask.request.args.get('speed_normal_phase', None) or flask.request.args.get('speed_normal_battery', None)) and flask.request.args.get('motor_power_constant', None)):
        return 'Cannot patch MPC and current at the same time. You gotta make a decision.'

    speed_params = (flask.request.args.get('speed_normal_kmh', None) or flask.request.args.get('speed_normal_phase', None) or flask.request.args.get('speed_normal_battery', None))
    if speed_params:
        speed_normal_kmh = 33
        speed_normal_phase = 55000
        speed_normal_battery = 25000
        if flask.request.args.get('speed_normal_kmh', None):
            speed_normal_kmh = int(flask.request.args.get('speed_normal_kmh', None))
            assert speed_normal_kmh >= 0 and speed_normal_kmh <= 100
        if flask.request.args.get('speed_normal_phase', None):
            speed_normal_phase = int(flask.request.args.get('speed_normal_phase', None))
            assert speed_normal_phase >= 0 and speed_normal_phase <= 65535
        if flask.request.args.get('speed_normal_battery', None):
            speed_normal_battery = int(flask.request.args.get('speed_normal_battery', None))
            assert speed_normal_battery >= 0 and speed_normal_battery <= 65535
        patcher.speed_params(speed_normal_kmh, speed_normal_phase, speed_normal_battery)

    stay_on_locked = flask.request.args.get('stay_on_locked', None)
    if stay_on_locked:
        patcher.stay_on_locked()

    remove_charging_mode = flask.request.args.get('remove_charging_mode', None)
    if remove_charging_mode:
        patcher.remove_charging_mode()

    swd_enable = flask.request.args.get('swd_enable', None)
    if swd_enable:
        patcher.swd_enable()

    bypass_BMS = flask.request.args.get('bypass_BMS', None)
    if bypass_BMS:
        patcher.bypass_BMS()
		
    bms_uart_76800 = flask.request.args.get('bms_uart_76800', None)
    if bms_uart_76800:
        patcher.bms_uart_76800()

    motor_power_constant = flask.request.args.get('motor_power_constant', None)
    if motor_power_constant is not None:
        motor_power_constant = int(motor_power_constant)
        assert motor_power_constant >= 20000 and motor_power_constant <= 65535
        patcher.motor_power_constant(motor_power_constant)

    cruise_control_delay = flask.request.args.get('cruise_control_delay', None)
    if cruise_control_delay is not None:
        cruise_control_delay = int(cruise_control_delay)
        assert cruise_control_delay >= 0 and cruise_control_delay <= 100
        patcher.cruise_control_delay(cruise_control_delay)

    motor_start_speed = flask.request.args.get('motor_start_speed', None)
    if motor_start_speed is not None:
        motor_start_speed = int(motor_start_speed)
        assert motor_start_speed >= 0 and motor_start_speed <= 10
        patcher.motor_start_speed(motor_start_speed)
		
    throttle_alg = flask.request.args.get('throttle_alg', None)
    if throttle_alg:
        patcher.alt_throttle_alg()

    version_spoofing = flask.request.args.get('version_spoofing', None)
    if version_spoofing:
         patcher.version_spoofing()

    output = flask.request.args.get('output', None)
    if output == 'zip' or not output:
        # make zip file for firmware
        zip_buffer = io.BytesIO()
        zip_file = zipfile.ZipFile(zip_buffer, 'a', zipfile.ZIP_DEFLATED, False)

        zip_file.writestr('FIRM.bin', patcher.data)
        md5 = hashlib.md5()
        md5.update(patcher.data)

        patcher.encrypt()
        zip_file.writestr('FIRM.bin.enc', patcher.data)
        md5e = hashlib.md5()
        md5e.update(patcher.data)

        info_txt = 'dev: ES/SNSC;\nnam: {};\nenc: B;\ntyp: DRV;\nmd5: {};\nmd5e: {};\n'.format(
            version, md5.hexdigest(), md5e.hexdigest())

        zip_file.writestr('info.txt', info_txt.encode())
        message = "Downloaded from scooterhacking.org - Share this CFW with the following link : https://max.scooterhacking.org"
        request_url = flask.request.full_path.encode()
        request_url = request_url.decode("utf-8").replace("cfw", "", 1).encode("utf-8")
        zip_file.comment = bytes(message, 'utf-8') + request_url
        zip_file.close()
        zip_buffer.seek(0)
        content = zip_buffer.getvalue()
        zip_buffer.close()

        resp = flask.Response(content)
        filename = version + '-' + str(int(time.time())) + '.zip'
        resp.headers['Content-Type'] = 'application/zip'
        resp.headers['Content-Disposition'] = 'inline; filename="{0}"'.format(filename)
        resp.headers['Content-Length'] = len(content)
    if output == 'bin' or output == 'enc':
        filename = version + '-' + str(int(time.time())) + '.bin'
        if output == 'enc':
            patcher.encrypt()
            filename += '.enc'
        resp = flask.Response(patcher.data)
        resp.headers['Content-Type'] = 'application/octet-stream'
        resp.headers['Content-Disposition'] = 'inline; filename="{0}"'.format(filename)
        resp.headers['Content-Length'] = len(patcher.data)

    return resp

if __name__ == '__main__':
    app.run('0.0.0.0')
