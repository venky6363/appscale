import logging
import psutil
import subprocess

from appscale.admin.service_manager import ServiceManager

logger = logging.getLogger('appscale-infrastructure-manager')

MOUNTPOINT_WHITELIST = ['/', '/opt/appscale', '/opt/appscale/backups',
  '/opt/appscale/cassandra', '/var/apps']

class JSONTags(object):
  # CPU related JSON tags.
  CPU = "cpu"
  IDLE = "idle"
  SYSTEM = "system"
  USER = "user"
  COUNT = "count"
  # Disk related JSON tags.
  DISK = "disk"
  TOTAL = "total"
  FREE = "free"
  USED = "used"
  # Memory related JSON tags.
  MEMORY = "memory"
  AVAILABLE = "available"
  # SWAP related JSON tags.
  SWAP = "swap"
  # Loadavg related JSON tags.
  LOADAVG = "loadavg"
  LAST_1_MIN = "last_1_min"
  LAST_5_MIN = "last_5_min"
  LAST_15_MIN = "last_15_min"
  RUNNABLE_ENTITIES = "runnable_entities"
  SCHEDULING_ENTITIES = "scheduling_entities"

class ServiceException(Exception):
  pass

class SystemManager():
  """ SystemManager class is the entry point for queries regarding system stats.

  This service reports statistics about disk, memory and CPU usage,
  Monit summary, and number of running appservers, if any.
  """

  def get_cpu_usage(self):
    """ Discovers CPU usage on this node.

    Returns:
      A dictionary containing the idle, system and user percentages.
    """

    cpu_stats = psutil.cpu_times_percent(percpu=False)
    cpu_stats_dict = { JSONTags.CPU :
      {
        JSONTags.IDLE : cpu_stats.idle,
        JSONTags.SYSTEM : cpu_stats.system,
        JSONTags.USER : cpu_stats.user,
        JSONTags.COUNT : len(psutil.cpu_times(percpu=True))
      }
    }
    logging.debug("CPU stats: {}".format(cpu_stats_dict))

    return cpu_stats_dict

  def get_disk_usage(self):
    """ Discovers disk usage per mount point on this node.

    Returns:
      A dictionary containing free bytes and bytes used per disk
      partition.
    """

    inner_disk_stats_dict = []
    relevant_mountpoints = [
      partition.mountpoint for partition in psutil.disk_partitions()
      if partition.mountpoint in MOUNTPOINT_WHITELIST]

    # Try at least to get overall disk usage.
    if not relevant_mountpoints:
      relevant_mountpoints.append('/')

    for partition in relevant_mountpoints:
      disk_stats = psutil.disk_usage(partition)
      partition_stats = {partition: {JSONTags.TOTAL: disk_stats.total,
                                     JSONTags.FREE: disk_stats.free,
                                     JSONTags.USED: disk_stats.used}}
      inner_disk_stats_dict.append(partition_stats)

    disk_stats_dict = { JSONTags.DISK : inner_disk_stats_dict }
    logging.debug("Disk stats: {}".format(disk_stats_dict))

    return disk_stats_dict

  def get_memory_usage(self):
    """ Discovers memory usage on this node.

    Returns:
      A dictionary containing memory bytes available and used.
    """

    mem_stats = psutil.virtual_memory()

    mem_stats_dict = { JSONTags.MEMORY :
      {
        JSONTags.TOTAL : mem_stats.total,
        JSONTags.AVAILABLE : mem_stats.available,
        JSONTags.USED : mem_stats.used
      }
    }
    logging.debug("Memory stats: {}".format(mem_stats_dict))

    return mem_stats_dict

  def get_service_summary(self):
    """ Retrieves Monit's summary on this node.

    Returns:
      A dictionary containing Monit's summary as a string.
    """

    try:
      monit_stats = subprocess.check_output(["monit", "summary"])
    except subprocess.CalledProcessError:
      logging.warn("get_service_summary: failed to query monit.")
      raise ServiceException('Failed to query monit.')

    monit_stats_dict = {}
    for line in monit_stats.split("\n"):
      tokens = line.split()
      if 'Process' in tokens:
        process_name = tokens[1][1:-1] # Remove quotes.
        process_status = ' '.join(tokens[2:]).lower()
        monit_stats_dict[process_name] = process_status
    logging.debug("Monit stats: {}".format(monit_stats_dict))

    # Get status of processes managed by the ServiceManager.
    monit_stats_dict.update(
      {'-'.join([server.type, str(server.port)]): server.state
       for server in ServiceManager.get_state()})

    return monit_stats_dict

  def get_swap_usage(self):
    """ Discovers swap usage on this node.

    Returns:
      A dictionary containing free bytes and bytes used for swap.
    """

    swap_stats = psutil.swap_memory()
    swap_stats_dict = { JSONTags.SWAP :
      {
        JSONTags.FREE : swap_stats.free,
        JSONTags.USED : swap_stats.used
      }
    }
    logging.debug("Swap stats: {}".format(swap_stats_dict))

    return swap_stats_dict

  def get_loadavg(self):
    """ Returns info from /proc/loadavg.
    See `man proc` for more details.

    Returns:
      A dictionary containing average load for last 1, 5 and 15 minutes,
      and information about running and scheduled entities,
      and PID of the most recently added process.
    """

    with open("/proc/loadavg") as loadavg:
      loadavg = loadavg.read().split()
    kernel_entities = loadavg[3].split("/")
    loadavg_stat = { JSONTags.LOADAVG :
      {
        JSONTags.LAST_1_MIN : float(loadavg[0]),
        JSONTags.LAST_5_MIN : float(loadavg[1]),
        JSONTags.LAST_15_MIN : float(loadavg[2]),
        JSONTags.RUNNABLE_ENTITIES : int(kernel_entities[0]),
        JSONTags.SCHEDULING_ENTITIES : int(kernel_entities[1])
      }
    }
    logging.debug("Loadavg stats: {}".format(' '.join(loadavg)))

    return loadavg_stat
