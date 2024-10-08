import logging
import sys
from signal import signal, SIGINT, SIGTERM

from rich.console import Console
from rich.logging import RichHandler

from pirogue_evidence_collector.frida.instrument_gated import FridaApplication

LOG_FORMAT = '%(message)s'
logging.basicConfig(level='INFO', format=LOG_FORMAT, handlers=[
    RichHandler(show_path=False, log_time_format='%X')])
console = Console()
log = logging.getLogger(__name__)


def dummy(a, b):
    pass


def finalize(app):
    log.info('Saving captured data')
    if app:
        app.save_data()
        log.info('You can analyze the results with the following commands in the output folder:')
        log.info('  * Generate a PCAPNG file: editcap --inject-secrets tls,sslkeylog.txt traffic.pcap decrypted.pcapng')
        log.info('  * Export decrypted traffic to JSON: tshark -2 -T ek --enable-protocol communityid -Ndmn -r decrypted.pcapng > traffic.json')
        log.info('  * View the decrypted traffic: pirogue-view-tls -i traffic.json')
        log.info('⚠️ depending on the configuration of your system you would have to run the commands with sudo.')
        sys.exit(0)


def start_interception():
    app = None
    try:
        app = FridaApplication()
        app.run()
    except KeyboardInterrupt:
        pass
    except Exception as e:
        log.error(e)
    finally:
        signal(SIGINT, dummy)
        signal(SIGTERM, dummy)
        log.info('Instrumentation stopped')
        finalize(app)
