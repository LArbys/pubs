import inspect
import copy
import psycopg2
import pubdb_env
import time
from pub_util        import pub_logger,pub_exception
from pubdb_exception import DBException
from pubdb_data      import pubdb_conn_info

class pubdb_conn(object):

    _conn_v  = []
    _conn_info_v = []
    _logger  = pub_logger.get_logger(__name__)
    debug    = _logger.debug
    info     = _logger.info
    warning  = _logger.warning
    error    = _logger.error
    critical = _logger.critical

    def __init__(self):
        self.warning('%s instance created by %s ' % (self.__class__,
                                                     inspect.stack()[1][3])
                     )
        self.warning('This is not needed as this is a factory class!')

    @classmethod
    def _check_conn_info_type(cls,conn_info):
        if not isinstance(conn_info,pubdb_conn_info):
            cls.critical('Input conn_info: %s not pubdb_conn_info type!' % conn_info)
            raise DBException()

    @classmethod
    def check_conn_info_exist(cls,conn_info,throw=False):
        cls._check_conn_info_type(conn_info)
        conn_index=-1
        for x in xrange(len(cls._conn_info_v)):
            if cls._conn_info_v[x] == conn_info:
                conn_index = x
                break
        if throw and conn_index < 0:
            cls.critical('Never existed connection: (%s,%s,%s,%s,XXX)' % (conn_info._host,
                                                                          conn_info._port,
                                                                          conn_info._db,
                                                                          conn_info._user))
            raise DBException('Invalid conn string provided')
            
        return conn_index

    @classmethod
    def close(cls,conn_info):

        if cls.closed(conn_info): return True

        conn_index = cls.check_conn_info_exist(conn_info,True)
        if conn_index < 0:
            return False
        else:
            cls._conn_v[conn_index].close()
            return bool(cls._conn_v[conn_index].closed)
        
    @classmethod
    def closed(cls,conn_info):

        conn_index = cls.check_conn_info_exist(conn_info,True)
        return cls._conn_v[conn_index].closed

    @classmethod
    def is_connected(cls,conn_info):

        if cls.closed(conn_info): 
            return False

        conn_index = cls.check_conn_info_exist(conn_info,True)
        valid_conn = False
        try:
            c = cls._conn_v[conn_index].cursor()
            c.execute('SELECT 1;')
            valid_conn = bool(c.rowcount)
            c.close()
        except Exception as e:
            pass
        return valid_conn

    @classmethod
    def _connect(cls,conn_info):

        conn_index=cls.check_conn_info_exist(conn_info)

        if conn_index >= 0 and cls.is_connected(conn_info):
            return conn_index
        
        # output on debug
        cls.debug( "PUBDB_CONN: db configuration" )
        cls.debug( "host: {}".format(conn_info._host) )
        cls.debug( "port: {}".format(conn_info._port) )
        cls.debug( "db: {}".format(conn_info._db) )
        cls.debug( "user: {}".format(conn_info._user) )
        #print "passwd",conn_info._passwd # seems like a bad idea

        now_str  = time.strftime('%Y-%m-%d %H:%M:%S')
        try:
            if conn_info._port:
                conn = psycopg2.connect(host=conn_info._host,
                                        port=conn_info._port,
                                        database=conn_info._db,
                                        user=conn_info._user,
                                        password=conn_info._passwd)
            else:
                conn = psycopg2.connect(host=conn_info._host,
                                        database=conn_info._db,
                                        user=conn_info._user,
                                        password=conn_info._passwd)
            cls.info('Connected to DB: (%s,%s,%s,%s,XXX) @ %s' % (conn_info._host,
                                                                  conn_info._port,
                                                                  conn_info._db,
                                                                  conn_info._user,
                                                                  now_str))

            if conn_info._role:
                cursor = conn.cursor()
                try:
                    cls.info('Setting ROLE = %s' % conn_info._role)
                    cursor.execute('SET ROLE %s;' % conn_info._role)
                    cursor.close()
                    del cursor
                except psycopg2.ProgrammingError as e:
                    cls.error(e.pgerror)
                    cursor.close()
                    cls.close(conn_info)
                    conn.close()
                    return conn_index

            if conn_index < 0:
                conn_index = len(cls._conn_v)
                cls._conn_v.append(conn)
                cls._conn_info_v.append(copy.copy(conn_info))
            else:
                cls._conn_v[conn_index] = conn

        except psycopg2.OperationalError as e:
            cls.error('Connection failed (%s,%s,%s,%s,XXX) @ %s ' % (conn_info._host,
                                                                     conn_info._port,
                                                                     conn_info._db,
                                                                     conn_info._user,
                                                                     now_str) )
        return conn_index

    @classmethod
    def connect(cls,conn_info):
        conn_index = cls._connect(conn_info)
        connected = bool(conn_index >= 0 and cls.is_connected(conn_info))
        ctr = conn_info._ntrial
        while not connected and ctr > 0:
            time.sleep(conn_info._sleep)
            conn_index = cls._connect(conn_info)
            connected  = bool(conn_index >= 0 and cls.is_connected(conn_info))
            ctr -= 1

        return connected

    @classmethod
    def reconnect(cls,conn_info):
        if not cls.close(conn_info):
            raise Exception()
        return cls.connect(conn_info)

    @classmethod
    def commit(cls,conn_info):
        if not cls.is_connected(conn_info): return False
        conn_index = cls.check_conn_info_exist(conn_info,True)
        cls._conn_v[conn_index].commit()
        return True

    @classmethod
    def cursor(cls,conn_info):
        if not cls.connect(conn_info):
            return None

        conn_index = cls.check_conn_info_exist(conn_info,True)
        return cls._conn_v[conn_index].cursor()



