---
layout: docs
title: System-wide Configuration
short_title: Configuration
---

## Location of the configuration file

To run the **docassemble** web application, you tell your web browser
to launch a WSGI file.  The standard WSGI file, `docassemble.wsgi`,
looks like this:

{% highlight python %}
import docassemble.webapp.config
docassemble.webapp.config.load(filename="/etc/docassemble/config.yml")
from docassemble.webapp.server import app as application
{% endhighlight %}

The first two lines load the **docassemble** configuration, and the
third imports the [Flask] application server.  The configuration is
stored in a [YAML] file, which by default is located in
`/etc/docassemble/config.yaml`.  If you wish, you can edit the WSGI
file and tell it to load the configuration from a file in a different
location.  You might want to do this if you have multiple virtual
hosts, each running a different WSGI application on a single server.

The configuration file needs to be readable by the web server, but
should not be readable by other users of the system because it may
contain sensitive information, such as Google and Facebook API keys.

## Configuration default values

{% highlight yaml %}
debug: false
root: /demo
exitpage: /
db:
  prefix: postgresql+psycopg2://
  name: docassemble
  user: none
  password: none
  host: none
  port: none
appname: docassemble
brandname: demo
uploads: /usr/share/docassemble/files
webapp: /var/lib/docassemble/docassemble.wsgi
mail:
  default_sender: None #'"Administrator" <no-reply@example.com>'
  username: none
  password: none
  server: localhost
  use_ssl: false
  use_tls: false
admin_address: none #'"Administrator" <admin@example.com>'
use_progress_bar: false
default_interview: docassemble.demo:data/questions/questions.yml
flask_log: /tmp/flask.log
language: en
locale: US.utf8
default_admin_account:
  nickname: admin
  email: admin@admin.com
  password: password
secretkey: 38ihfiFehfoU34mcq_4clirglw3g4o87
png_resolution: 300
png_screen_resolution: 72
show_login: true
initial_dict:
  url_args: {}
{% endhighlight %}

By default, `imagemagick`, `pdftoppm_command`, and `oauth` are
undefined.

## Enabling optional features

If you have ImageMagick and pdftoppm installed on your system, you
need to tell **docassemble** the names of the commands to use.

{% highlight yaml %}
imagemagick: convert
pdftoppm_command: pdftoppm
{% endhighlight %}

If you want to enable logging in with Facebook or with Google, you
will need to tell **docassemble** your oauth keys:

{% highlight yaml %}
oauth:
  facebook:
    enable: true
    id: 423759825983740
    secret: 34993a09909c0909b9000a090d09f099
  google:
    enable: true
    id: 23123018240-32239fj28fj4fuhf394h3984eurhfurh.apps.googleusercontent.com
    secret: DGE34gdgerg3GDG545tgdfRf
{% endhighlight %}

You can disable these login methods by setting `enable` to false.

You can also set a default currency symbol if the symbol generated by
the locale is not what you want:

{% highlight yaml %}
currency_symbol: €
{% endhighlight %}

This symbol will be used in the user interface when a field has the
`datatype` of `currency`.  It will also be used in the
`currency_symbol()` function defined in `docassemble.base.util`.

[Flask]: http://flask.pocoo.org/
[YAML]: [YAML]: https://en.wikipedia.org/wiki/YAML