import imp
import json
import subprocess
import os

import bottle as bot

from server_backend import UpdateMgmt


app = bot.Bottle()


html_page = """
<html>
<head>
<title></title>
</head>
<body>
{}
</body>
</html>
"""

um = UpdateMgmt()
u2 = UpdateMgmt()
u3 = UpdateMgmt()

@app.route('/system_update')
def system_update():
    body = """
    <form method="POST" action="/status_update">
        Controller Hostname: <input name="hostname" type="text" /><br />
        Setup Details: <input name="setup_details" type="text" value="LAST_SUCESSFUL_BUILD"/><br />
        <input type="submit" />
    </form>
    <p>Last Ten Updates:</p>
    {}
    """
    loglines = ''
    for line in um.get_loglines().splitlines()[-10:]:
        loglines += '<p>{}</p>'.format(line)

    return bot.template(html_page.format(body.format(loglines)))

@app.route('/system_update/fulllog')
def system_update():
    body = """
    {}
    """
    loglines = ''
    for line in um.get_loglines().splitlines():
        loglines += '<p>{}</p>'.format(line)

    return bot.template(html_page.format(body.format(loglines)))


@app.post('/status_update', methods=["POST"])
def update_controller():
    hostname = bot.request.forms.get('hostname')
    setup_details = bot.request.forms.get('setup_details')

    build = setup_details
    if setup_details == "LAST_SUCESSFUL_BUILD":
        build = 'txt'

    result = {'hostname': hostname, 'setup_details_link': build}
    um.add_job(result)

    body = """
    <p>Running ppkg update on {host}</p>
    <p>Using build from {build}</p>
    <p>Please be patient and return to previous page for status</p>
    """.format(host=hostname, build=build)

    return bot.template(html_page.format(body))

try:
    print 'Commands PID:', os.getpid()

    bot.run(app, host='localhost', port=8080, debug=True)
except:
    um.stop()
    um.join()

