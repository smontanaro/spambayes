#include <stdio.h>
#include <stdlib.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <sys/stat.h>
#include <errno.h>
#include <fcntl.h>

extern char *optarg;
extern int optind;

#define ARGV_FOR_SERVER_LEN 30
const char *argv_for_server[ARGV_FOR_SERVER_LEN];
int argv_for_server_len = 0;

const char *socket_filename = NULL;

#define CMDLINE_FOR_ACTION_LEN 1024
char cmdline_for_action[CMDLINE_FOR_ACTION_LEN] = "";
int cmdline_for_action_len = 0;

static void usage(int code,const char *message)
{
    if(message)
    {
        fputs(message,stderr);
    }
    fprintf(stderr,"FIXME: usage info goes in here\n");
    exit(code);
}

static void add_argv_to_server(const char *a)
{
    if(argv_for_server_len+2 > ARGV_FOR_SERVER_LEN)
    {
        usage(2, "Error: too many arguments for server\n");
    }
    argv_for_server[argv_for_server_len+0] = a;
    argv_for_server[argv_for_server_len+1] = NULL;
    ++argv_for_server_len;
}

static void add_argv_to_action(const char *a)
{
    int length = strlen(a);
    if(cmdline_for_action_len+2+length > CMDLINE_FOR_ACTION_LEN)
    {
        usage(2, "Error: too many arguments for action\n");
    }
    if(cmdline_for_action_len)
    {
        cmdline_for_action[cmdline_for_action_len++] = ' ';
    }
    strcpy(cmdline_for_action+cmdline_for_action_len, a);
    cmdline_for_action_len += length;
}


static int exists(const char *filename)
{
    struct stat junk_stat_buf;
    if(stat(filename,&junk_stat_buf))
    {
        if(errno==ENOENT)
        {
            return 0;
        }
    }
    return 1;
}

static const char *find_server(const char *filter)
{
    /* where might our server be, relative to this program ? */
    const char *suffix1 = "../libexec/sb_bnserver.py";    /* in /usr/libexec. I guess thats the right place when installed */
    const char *suffix2 = "../scripts/sb_bnserver.py";    /* running from cvs checkout, and compiled into the same directory as our source */
    const char *suffix3 = "sb_bnserver.py";               /* in /usr/bin. not ideal, but likely to happen anyway */
    
    int i = strlen(filter);
    char *server = malloc(i+strlen(suffix1)+1);   /* suffix1 is the longest */
    if(!server)
    {
        perror("malloc of server filename");
        exit(3);
    }
    /* copy the filter filename */
    strcpy(server,filter);
    /* find the position of the trailing directory seperator, or the start of the string if there isnt one */
    for(;i>0;--i)
    {
        if(server[i-1]=='/') break;
    }
    /* try each one in turn */
    strcpy(server+i,suffix1);
    if(exists(server))
        return server;
    strcpy(server+i,suffix2);
    if(exists(server))
        return server;
    strcpy(server+i,suffix3);
    if(exists(server))
        return server;
    fprintf(stderr,"Cant find sb_bnserver.py\n");
    exit(3);
}

static void init_socket_filename()
{
    char hostname[256];
    const char *home = getenv("HOME");
    const char *intermediate = "/.sbbnsock-";
    char *filename;
    if(!home)
    {
        usage(3,"HOME environment variable not defined");
    }
    if(gethostname(hostname,256))
    {
        perror("gethostname");
        exit(3);
    }
    socket_filename = filename = malloc(strlen(hostname)+strlen(intermediate)+strlen(home)+1);
    if(!socket_filename)
    {
        perror("malloc of socket_filename");
        exit(3);
    }
    strcpy(filename,home);
    strcat(filename,intermediate);
    strcat(filename,hostname);
}

static void process_argv(int argc,const char **argv)
{
    int opt;
    while(-1 != (opt = getopt(argc,argv,"hfgstGSd:p:o:a:A:k:y")))
    {
        switch(opt)
        {
            case '?':
            default:
                usage(2,NULL);
                break;
            case 'h':
                usage(0,NULL);
                break;
            case 'd':
                add_argv_to_server("-d");
                add_argv_to_server(optarg);
                break;
            case 'p':
                add_argv_to_server("-p");
                add_argv_to_server(optarg);
                break;
            case 'o':
                add_argv_to_server("-o");
                add_argv_to_server(optarg);
                break;
            case 'a':
                add_argv_to_server("-a");
                add_argv_to_server(optarg);
                break;
            case 'A':
                add_argv_to_server("-A");
                add_argv_to_server(optarg);
                break;
            case 'y':
                add_argv_to_server("-y");
                break;
            case 'f':
                add_argv_to_action("-f");
                break;
            case 'g':
                add_argv_to_action("-g");
                break;
            case 's':
                add_argv_to_action("-s");
                break;
            case 't':
                add_argv_to_action("-t");
                break;
            case 'G':
                add_argv_to_action("-G");
                break;
            case 'S':
                add_argv_to_action("-S");
                break;
            case 'k':
                socket_filename = optarg;
                break;
        }
    }
    if(optind!=argc)
    {
        usage(2, "Error: unrecognised arguments\n");
    }
}

static void fork_server()
{
    if(fork())
    {
        /* parent */
        return;
    }
    /* child */
    close(0); open("/dev/null",O_RDONLY);
    /*close(1); open("/dev/null",O_WRONLY);*/
    setsid();
    execvp(argv_for_server[0],argv_for_server);
    perror("failed to exec python");
}

static int make_socket()
{
    int refused_count = 0;
    int no_server_count = 0;
    int s;
    int sleep_time;
    int saved_errno;
    struct sockaddr_un addr_un;
    
    while(1)
    {
        s = socket(AF_UNIX,SOCK_STREAM,0);
        if(s>=0)
        {
            if(strlen(socket_filename)>sizeof(addr_un.sun_path))
            {
                usage(3,"socket name too long");
            }
            addr_un.sun_family = AF_UNIX;
            memcpy(addr_un.sun_path, socket_filename, sizeof(addr_un.sun_path));
            if(!connect(s,(struct sockaddr *)&addr_un,sizeof(addr_un)))
            {
                return s;
            }
        }
        /* drop-through means we didnt connect */
        saved_errno = errno;
        if(saved_errno==EAGAIN)
        {
            /* baaaah */
        }
        else if(saved_errno == ENOENT || !exists(socket_filename))
        {
            ++no_server_count;
            if(no_server_count>4)
            {
                fprintf(stderr, "Cant see server... sb_bnfilter giving up");
                exit(4);
            }
            fork_server();
        }
        else if(saved_errno == ECONNREFUSED)
        {
            ++refused_count;
            if(refused_count == 6)
            {
                unlink(socket_filename);
            }
            if(refused_count>6)
            {
                fprintf(stderr, "Cant connect to server... sb_bnfilter giving up\n");
                exit(4);
            }
        }
        else
        {
            fprintf(stderr, "Unexpected error %d... sb_bnfilter giving up\n", saved_errno);
            exit(4);
        }
        if(refused_count+no_server_count > 2)
            /* use sleep if sleeping for more than one second */
            sleep(1<<(refused_count+no_server_count-2));
        else
            /* use usleep if less */
            usleep(200000<<(refused_count+no_server_count));
    }
}

void do_pipe(int s_fd)
{
    int expected_size, total_size=0, error_code;
    FILE *output;
    char buf[4096];
    FILE *f = fdopen(s_fd,"w+");
    fprintf(f,"%s\n",cmdline_for_action);
    while(!feof(stdin))
    {
        int i = fread(buf,1,4096,stdin);
        if(ferror(stdin))
        {
            perror("reading from stdin");
            exit(3);
        }
        if(i!=fwrite(buf,1,i,f))
        {
            perror("writing to pipe");
            exit(3);
        }
    }
    if(fflush(f))
    {
        perror("writing to pipe");
        exit(3);
    }

    shutdown(s_fd,1);    
    
    if(2!=fscanf(f,"%d\n%d\n",&error_code,&expected_size))
    {
        perror("reading size from pipe");
        exit(3);
    }
    
    output = ((error_code)?(stderr):(stdout));
    
    while(!feof(f))
    {
        int i = fread(buf,1,4096,f);
        if(ferror(f))
        {
            perror("reading from pipe");
            exit(3);
        }
        if(i!=fwrite(buf,1,i,output))
        {
            perror("writing to output");
            exit(3);
        }
        total_size += i;
    }
    if(fflush(output))
    {
        perror("writing to output");
        exit(3);
    }
    
    if(total_size!=expected_size)
    {
        fprintf(stderr,"Size mismatch, %d != %d\n", total_size, expected_size);
        exit(3);
    }
    
    if(error_code)
    {
        exit(error_code);
    }
}

int main(int argc,const char **argv)
{
    add_argv_to_server("python");
    add_argv_to_server(find_server(argv[0]));
    init_socket_filename();
    process_argv(argc,argv);
    add_argv_to_server(socket_filename);
    do_pipe(make_socket());
    return 0;
}

