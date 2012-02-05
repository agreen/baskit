import os
import sys
import re
from zipfile import ZipFile
from commands import getoutput as run
from ConfigParser import ConfigParser

from world import World
import mc
import screen

def compress_folder(zip_filename, location, from_loc=None, excludes=[]):
    zfile = ZipFile(zip_filename, 'a')
    for dirpath, dirs, files in os.walk(location):
        for f in files:
            excluded = False
            fn = os.path.join(dirpath, f)
            arc_name = fn.replace(from_loc, '')
            if fn in excludes:
                continue
            zfile.write(fn, arc_name)
    zfile.close()

class Server(object):
    name = 'default'
    java_args = ''
    env = './'
    binary = 'server.jar'
    server_type = 'vanilla'
    server_branch = 'stable'
    server_build = '1.0'
    worlds = []
    _config_file = 'baskit.conf'
    
    def __init__(self, name, config_file='baskit.conf'):
        '''Baskit server initialization
        '''
        self.name = name
        if not os.path.exists(config_file):
            config_file = '%s/.baskit.conf' % sys.env['HOME']
        if not os.path.exists(config_file):
            config_file = '/etc/baskit.conf'
        if not os.path.exists(config_file):
            self.set_config()
        self._config_file = config_file
        self.get_config()
    
    def running(self):
        '''running
        Returns True/False whether the server is running or not.
        '''
        return screen.exists('mc_%s' % self.name):
    
    def get_config(self, config_file=None):
        '''get_config
        Fetches the configuration for the server and adjusts the variables
        within the server object to match the configuration.
        '''
        
        # Initializing the configration parser and reading the config file.
        config = ConfigParser()
        if config_file == None:
            config_file = self._config_file
        config.read(config_file)
        
        # Setting the section name and fetching the information from the
        # configuration file and applying those values to the appropriate
        # object variable.
        section = 'Server: %s' % self.name
        self.java_args = config.get(section, 'java_args')
        self.binary = config.get(section, 'binary')
        self.env = config.get(section, 'environment')
        self.server_type = config.get(section, 'server_type')
        self.server_branch = config.get(section, 'server_branch')
        self.server_build = config.get(section, 'server_build')
        self.min_mem = config.get(section, 'min_mem')
        self.max_mem = config.get(section, 'max_mem')
        
        # Linking in the worlds that we are aware of to the server
        # configuration.  This is normally entirely optional unless you would
        # like to use the backup & restore functions, or if you would like to
        # use ramdisks.
        for world_name in config.get(section, 'worlds').split(','):
            world_name = world_name.strip()
            self.worlds.append(World(world_name))
    
    def set_config(self):
        '''set_config
        Commits the current configuration of the server object to the config
        file.  This i also useful in generating a new configuration
        declaration if this is a new installation or if you will be running
        multiple servers.
        '''
        
        # Initializing the configuration parser and reading in the existing
        # data if there is any.
        config = ConfigParser()
        if os.path.exists(self._config_file):
            config.read(self._config_file)
        
        # Setting the section name and commiting the variables to the config
        # file.
        section = 'Server: %s' % self.name
        config.set(section, 'binary', self.binary)
        config.set(section, 'environment', self.env)
        config.set(section, 'server_type', self.server_type)
        config.set(section, 'server_branch', self.server_branch)
        config.set(section, 'server_build', self.server_build)
        config.set(section, 'min_memory', self.min_mem)
        config.set(section, 'max_memory', self.max_mem)
        config.set(section, 'java_args', self.java_args)
        
        # Now to get the list of world names that are configured with this
        # server and add them to the 'worlds' option in the configuration
        # stanza.
        wnames = []
        for world in self.worlds:
            wnames.append(world.name)
        config.set(section, 'worlds', ', '.join(wnames))
        
        # Lastly, we need to write the config file to disk.
        with open(self._config_file, 'wb') as configfile:
            config.write(configfile)
        
    
    def command(self, command, restring=None):
        '''command [command]
        Sends the specified command to the server console and will optionally
        wait for a given regex to return a match from the server.log before
        returning.
        '''
        
        if restring is not None:
            # If a regex was specified for interactivity, then we will need
            # to open the server.log file and seek to the end of the file
            # before we actually do anything.  Once we send the command that
            # was specified we will use the end of the file as a starting
            # point for the parsing.
            relog = re.compile(restring)
            logfile = open(os.path.join(self.env, 'env', 'server.log'), 'r')
            size = os.stat(os.path.join(self.env, 'env', 'server.log'))[6]
            logfile.seek(size)
        
        # Sending the command to the screen session
        screen.send('mc_%s' % self.name, command)
        
        if restring is not None:
            # Now we will start parsing through all of the log data that the
            # server is returning, using the now old EOF as a starting point.
            # We will run the regex that we had compiled to the relog variable
            # on every line until we get a match, then return those matches.
            found = False
            while not found:
                where = logfile.tell()
                line - logfile.readline()
                if not line:
                    time.sleep(0.1)
                    logfile.seek(where)
                else:
                    if len(relog.findall(line)) > 0:
                        found = True
            logfile.close()
            return relog.findall(line)
        
        # If there was no regex specified, then there is nothing to return.
        return None  
    
    def start(self):
        '''start
        Starts the Minecraft server and runs any per-world initialization.
        '''
        
        # First thing, we need to check to make sure the server isnt running,
        # we don't want to create any oddness as a result of running two
        # identically configured servers.
        if not self.running():
            
            # Next we will run the per-world initialization.  Normally this
            # shouldn't do anything, however if the worlds are stored on
            # ramdisks then there will be some useful setup stuff happening.
            for world in self.worlds:
                world.init()
            
            # Now just to setup all the variables, determine which java we
            # will be running, and to build the bash command that we will send
            # to screen to startup the server.
            renv = os.path.join(self.env, 'env')
            java = run('which java')
            startup = 'cd %s;%s %s -Xms%sm -Xmx%sm -jar %s nogui' % (renv,
                                                               java,
                                                               self.java_args,
                                                               self.min_mem,
                                                               self.max_mem, 
                                                               self.binary)
            # And here we go, startup time!
            screen.new('mc_%s' % self.name, startup)
    
    def stop(self):
        '''stop
        Tells the minecraft server to stop.
        '''
        # First thing we will need to is tell the server to stop and wait for
        # the server to finish shutting down.
        self.console('stop')
        while self.running():
            time.sleep(0.1)
        
        # Then we will run the cleanup on every world.  Just like world inits,
        # generally there shouldn't be much going on here, however if there
        # are ramdisk worlds, then we will be performing some actions here in
        # order to properly cleanup and make sure all the ramdisk data is
        # synced.
        for world in self.worlds:
            world.cleanup()
    
    def players(self):
        '''players
        Returns the list of currently commected players
        '''
        repl = re.compile(r' ([^,]*)')
        line = console('listt', r'Connected players:(.*)').strip('\n')
        players = repl.findall(line)
        return players
    
    def update(self, build_type='stable', bin_type=None):
        if self.running():
            return False
        
        if bin_type == None:
            bin_type = self.server_type
        
        # Download the new server binary
        binary = mc.download(bin_type, build_type)
        
        # Setting the new variable definitions...
        self.server_type = binary['server_type']
        self.server_branch = binary['branch']
        self.server_build = binary['build']
        
        # Lastly, write the new data to disk and commit the config changes.
        with open(os.path.join(self.env, 'env', self.binary), 'wb') as bin:
            bin.write(binary['binary'])
        self.set_config()
        
        return True # We have to return something so that we know it worked ;)
        
    def world_backup(self, world_name, backup_name=None):
        '''backup [world name], [backup_name]
        Runs the backup procedure for the specified world.
        '''
        # If there is no name specified, then go ahead and create one using
        # the current date & time.
        if backup_name == None:
            backup_name = '%s_%s' % (world_name, 
                            datetime.datetime.now().strftime('%Y-%m-%d_%H%M'))
        
        # Perform a save-all & save-off before we run the backup to write all
        # changes to disk.
        self.command('save-all')
        self.command('save-off')
        
        # Now walk through the worlds until we find a name match and run the
        # compress_folder function to generate the zip file archive.
        for world in self.worlds:
            if world.name == world_name:
                world.sync()
                compress_folder(os.path.join(self.env, 'archive', 'backups', 
                                             '%s.zip' % backup_name), 
                                os.path.join(self.env, 'env', world_name),
                                os.path.join(self.env, 'env', world_name))
    
    def env_snapshot(self, snap_name=None):
        '''snapshot [snapshot name]
        Generates a Snapshot zip file
        '''
        # If there is no name specified, then go ahead and create one using
        # the current date & time.
        if snap_name == None:
            snap_name = '%s_%s' % (self.name,
                            datetime.datetime.now().strftime('%Y-%m-%d_%H%M'))
        
        # Now we need to build the exclusion list.  This list will contain all
        # of the files for each world.  This is needed as we do not want to
        # archive the world data as part of a snapshot.
        excludes = []
        for world in self.worlds:
            world_path = os.path.join(self.env, 'env', world.name)
            for dirname, dirs, files in os.walk(world_path):
                for f in files:
                    excludes.append(os.path.join(dirname, f))
        
        # And now we run the compress_folder function to generate the archive.
        compress_folder(os.path.join(self.env, 'archive', 'snaps',
                                     '%s.zip' % snap_name),
                        os.path.join(self.env, 'env'),
                        os.path.join(self.env, 'env'),
                        excludes)
                        
        # Now we need to add the baskit configuration file to the snapshot.
        zfile = ZipFile(os.path.join(self.env, 'archive', 'snaps',
                        '%s.zip' % snap_name))
        zfile.write(self._config_file, 'baskit.config')
    
    def env_snap_restore(self, snap_name):
        '''snap_restore [snapshot name]
        Restores a snapshot zipfile.
        '''
        if not self.running():
            # If the server isn't running, then we will extract the contents
            # of the zipfile in place of the current environment.  This means
            # that we will first be deleting all of the existing data
            # associated with this environment before laying the backup into
            # it's place.
            
            # World exclusion list.  We love our worlds and don't wanna see
            # them die ^_^
            exclusion_list = []
            for world in self.worlds:
                world_path = os.path.join(self.env, 'env', world.name)
                for dirname, dirs, files in os.walk(world_path):
                    for f in files:
                        exclusion_list.append(os.path.join(dirname, f))
            
            # And here comes the deleting ;)
            for dirname, dirs, files, in os.walk(self.env):
                for f in files:
                    fn = os.path.join(dirname, f)
                    if fn not in exclusion_list:
                        os.remove(fn)
            
            # Now we extract the snapshot into our nice clean environment ;)
            zfile = ZipFile(os.path.join(self.env, 'archive', 'snaps', 
                                         '%s.zip' % snap_name))
            zfile.extractall(os.path.join(self.env, 'env'))
            
            # Now that all of the data is extracted, we need to tell the
            # environment to read it's configuration back in.  Please note
            # that the environment names MUST match for this import to
            # properly work.
            self.get_config(os.path.join(self.env, 'baskit.config'))
            self.set_config()
            
            # Lastly we will remove the now un-needed baskit.config file.
            os.remove(os.path.join(self.env, 'baskit.config'))
            return True
        else:
            return False
    
    def world_restore(self, backup_name, world_name):
        '''world_restore [backup name]
        Restores a world backup.  If restoring to a new world, then the
        associated world object will be created.
        '''
        if not self.running():
            # If the server isn't running, then we will extract the world
            # backup to the world name that was provided.  We will first clean
            # out all of the existing data to make sure that we are applying
            # the backup cleanly.
            
            # First we need to check to see if there is an existing folder
            # for the world data to reside in, if there isnt one, then create
            # it.
            world_path = os.path.join(self.env, 'env', world_name)
            if not os.path.exists(world_path):
                os.mkdir(world_path)
            
            # Lets clean out the current world data to make way for a nice
            # new world.
            for dirname, dirs, files in os.walk(world_path):
                for f in files:
                    os.remove(os.path.join(dirname, f))
            
            # Now lets unzip the backup...
            zfile = ZipFile(os.path.join(self.env, 'archive', 'backups',
                                         '%s.zip' % backup_name))
            zfile.extractall(world_path)
            
            # Lastly lets check to see if this world name exists in our config
            # and create the world object if needed.
            exists = False
            for world in self.worlds:
                if world.name == world_name:
                    exists = True
            if not exists:
                self.worlds.append(World(world_name, self.env))
                self.set_config()
            return True
        else:
            return False