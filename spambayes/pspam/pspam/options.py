from Options import options, all_options, \
     boolean_cracker, float_cracker, int_cracker, string_cracker
from sets import Set     

all_options["Score"] = {'max_ham': float_cracker,
                        'min_spam': float_cracker,
                        }

all_options["Train"] = {'folder_dir': string_cracker,
                        'spam_folders': ('get', lambda s: Set(s.split())),
                        'ham_folders': ('get', lambda s: Set(s.split())),
                        }

all_options["Proxy"] = {'server': string_cracker,
                        'server_port': int_cracker,
                        'proxy_port': int_cracker,
                        'log_pop_session': boolean_cracker,
                        'log_pop_session_file': string_cracker,
                        }

all_options["ZODB"] = {'zeo_addr': string_cracker,
                       'event_log_file': string_cracker,
                       'event_log_severity': int_cracker,
                       'cache_size': int_cracker,
                       }

import os
options.mergefiles("vmspam.ini")

def mergefile(p):
    options.mergefiles(p)
