from __future__ import with_statement # needed for python 2.5
from fabric.api import *
from fabric.contrib.files import exists

# globals
env.project_name = 'myprojectname' # no spaces!
env.dbserver = 'mysql' # mysql or postgresql
env.port = 8080 # local FCGI server

def production():
    "Use the production webserver"
    env.domain = 'production.mydomain.com' # domain name
    env.hosts = ['1.1.1.1'] # ip address or server domain
    env.user = ''
    env.deployment = 'production'    
    env.path = '/data/vhost/%(project_name)s-production' % env
    env.virtualhost_path = env.path
    env.pysp = '%(virtualhost_path)s/lib/python2.5/site-packages' % env

def staging():
    "Use the staging webserver"
    env.domain = 'staging.mydomain.com'  # domain name
    env.hosts = ['1.1.1.1']
    env.user = ''
    env.path = '/data/vhost/%(project_name)s-staging' % env
    env.virtualhost_path = env.path
    env.deployment = 'staging'
    env.pysp = '%(virtualhost_path)s/lib/python2.5/site-packages' % env    

def setup():
    """
    Setup a fresh virtualenv as well as a few useful directories, then run
    a full deployment
    """
    require('hosts', provided_by=[staging, production])
    require('deployment', provided_by=[staging, production])    
    require('path')
    # install Python environment
    sudo('apt-get install -y build-essential python-dev python-setuptools python-imaging')
    # install some version control systems, since we need Django modules in development
    sudo('apt-get install -y git-core') # subversion git-core mercurial

    # install more Python stuff
    sudo('easy_install -U setuptools')
    sudo('easy_install pip')
    sudo('pip install -U virtualenv')
    
    # install webserver and database server
    sudo('apt-get remove -y apache2 apache2-mpm-prefork') # is mostly pre-installed
    sudo('apt-get install -y apache2')
    sudo('apt-get install -y libapache2-mod-wsgi') # outdated on hardy!
    if env.dbserver=='mysql':
        sudo('apt-get install -y mysql-server python-mysqldb')
    elif env.dbserver=='postgresql':
        sudo('apt-get install -y postgresql python-psycopg2')
        
    # disable default site
    with settings(warn_only=True):
        sudo('cd /etc/apache2/sites-enabled/; rm default;' % env, pty=True)
    
    # new project setup
    sudo('mkdir -p %(path)s; chown %(user)s:%(user)s %(path)s;' % env, pty=True)
    with settings(warn_only=True):
        run('cd ~; ln -s %(path)s www;' % env, pty=True) # symlink web dir in home
    with cd(env.path):
        run('virtualenv .')
        with settings(warn_only=True):
            run('mkdir -m a+w logs; mkdir releases; mkdir config; mkdir shared; mkdir packages; mkdir backup;' % env, pty=True)
            run('cd releases; ln -s . current; ln -s . previous;', pty=True)

            # write the default wsgi file
            if not exists('config/%(project_name)s.wsgi' % env):
                run('touch config/%(project_name)s.wsgi' % env, pty=True)
                run("echo 'import os' > config/%(project_name)s.wsgi" % env, pty=True)        
                run("echo 'import sys' >> config/%(project_name)s.wsgi" % env, pty=True)        
                run("echo 'sys.path.insert(0, os.path.abspath(\"%(path)s/releases/current/%(project_name)s\"))' >> config/%(project_name)s.wsgi" % env, pty=True)        
                run("echo 'os.environ[\"DJANGO_SETTINGS_MODULE\"] = \"settings\"' >> config/%(project_name)s.wsgi" % env, pty=True)        
                run("echo 'from django.core.handlers.wsgi import WSGIHandler' >> config/%(project_name)s.wsgi" % env, pty=True)                                                            
                run("echo 'application = WSGIHandler()' >> config/%(project_name)s.wsgi" % env, pty=True)

            # write the default apache config file TODO: create the user/group if they don't exist
            if not exists('config/apache2.conf'):
                run('touch config/apache2.conf', pty=True)
                run("echo '<VirtualHost *:80>' >> config/apache2.conf", pty=True)        
                run("echo '        ServerName  %(domain)s' >> config/apache2.conf" % env, pty=True)                        
                run("echo '        WSGIDaemonProcess %(project_name)s-%(deployment)s user=%(project_name)s-%(deployment)s group=django-%(deployment)s threads=10 python-path=%(path)s/lib/python2.5/site-packages' >> config/apache2.conf" % env, pty=True)                        
                run("echo '        WSGIProcessGroup %(project_name)s-%(deployment)s' >> config/apache2.conf" % env, pty=True)                        
                run("echo '        WSGIScriptAlias / %(path)s/releases/current/%(project_name)s.wsgi' >> config/apache2.conf" % env, pty=True)                        
                run("echo '        <Directory %(path)s/releases/current/%(project_name)s>' >> config/apache2.conf" % env, pty=True)                        
                run("echo '           Order deny,allow' >> config/apache2.conf", pty=True)
                run("echo '           Allow from all' >> config/apache2.conf", pty=True)
                run("echo '        </Directory>' >> config/apache2.conf", pty=True)
                run("echo '        LogLevel warn' >> config/apache2.conf", pty=True)
                run("echo '</VirtualHost>' >> config/apache2.conf", pty=True)
                
            #write the default local_settings file
            if not exists('config/local_settings.py'):
                put('%(project_name)s/local_settings.py.git' % env, '%(path)s/config/local_settings.py' % env)            

            # create user & group
            with settings(warn_only=True):                    
                sudo('groupadd django-%(deployment)s' % env, pty=True)        
                sudo('useradd -g django-%(deployment)s %(project_name)s-%(deployment)s' % env, pty=True)                        

            #what to do next ...
            print "If this is the first time you have run this command you need to ..."
            print "1) Create a new database + database user"
            print "2) Edit the config/local_settings.py file"
            print "3) Deploy"            


def deploy():
    """
    Deploy the latest version of the site to the servers, install any
    required third party modules, install the virtual host and 
    then restart the webserver
    """
    require('hosts', provided_by=[staging, production])
    require('path')
    import time
    env.release = time.strftime('%Y%m%d%H%M%S')
    upload_tar_from_git()
    install_requirements()
    install_site()
    symlink_current_release()
    migrate()
    restart_webserver()
    
def deploy_version(version):
    "Specify a specific version to be made live"
    require('hosts', provided_by=[staging, production])
    require('path')
    env.version = version
    with cd(env.path):
        run('rm -rf releases/previous; mv releases/current releases/previous;', pty=True)
        run('ln -s %(version)s releases/current' % env, pty=True)
    restart_webserver()

def rollback():
    """
    Limited rollback capability. Simply loads the previously current
    version of the code. Rolling back again will swap between the two.
    """
    require('hosts', provided_by=[staging, production])
    require('path')
    with cd(env.path):
        run('mv releases/current releases/_previous;', pty=True)
        run('mv releases/previous releases/current;', pty=True)
        run('mv releases/_previous releases/previous;', pty=True)
    restart_webserver()    
    
# Helpers. These are called by other functions rather than directly

def upload_tar_from_git():
    "Create an archive from the current Git master branch and upload it"
    require('release', provided_by=[deploy, setup])
    require('deployment', provided_by=[production, staging])    

    local('git archive --format=tar master | gzip > %(release)s.tar.gz' % env)
    run('mkdir -p %(path)s/releases/%(release)s' % env, pty=True)
    put('%(release)s.tar.gz' % env, '%(path)s/packages/' % env)
    run('cd %(path)s/releases/%(release)s && tar zxf ../../packages/%(release)s.tar.gz' % env, pty=True)
    local('rm %(release)s.tar.gz' % env)

def install_site():
    "Add the virtualhost config file to the webserver's config"
    require('release', provided_by=[deploy, setup])
    with cd('%(path)s/releases/%(release)s' % env):

        #copy over config files
        sudo('cp %(path)s/config/%(project_name)s.wsgi %(path)s/releases/%(release)s/%(project_name)s.wsgi'  % env, pty=True)
        sudo('cp %(path)s/config/local_settings.py %(path)s/releases/%(release)s/%(project_name)s/local_settings.py'  % env, pty=True)        
        sudo('cp %(path)s/config/apache2.conf /etc/apache2/sites-available/%(project_name)s-%(deployment)s' % env, pty=True)


        # try logrotate
        with settings(warn_only=True):        
            sudo('cp logrotate.conf /etc/logrotate.d/website-%(project_name)s' % env, pty=True)
    with settings(warn_only=True):        
        sudo('cd /etc/apache2/sites-enabled/; ln -s ../sites-available/%(project_name)s-%(deployment)s %(project_name)s-%(deployment)s' % env, pty=True)

def install_requirements():
    "Install the required packages from the requirements file using pip"
    require('release', provided_by=[deploy, setup])
    run('cd %(path)s; pip install -E . -r ./releases/%(release)s/requirements.txt' % env, pty=True)

def symlink_current_release():
    "Symlink our current release"
    require('release', provided_by=[deploy, setup])
    with cd(env.path):
        run('rm releases/previous; mv releases/current releases/previous;', pty=True)
        run('ln -s %(release)s releases/current' % env, pty=True)

def migrate():
    "Update the database"
    require('project_name')
    require('path')
    run('cd %(path)s/releases/current/%(project_name)s; %(path)s/bin/python manage.py syncdb --noinput' % env, pty=True)
    run('cd %(path)s/releases/current/%(project_name)s; %(path)s/bin/python manage.py migrate --noinput' % env, pty=True)    

def restart_webserver():
    "Restart the web server"
    sudo('/etc/init.d/apache2 reload' % env, pty=True)