from apscheduler.schedulers.background import BackgroundScheduler
from django_apscheduler.jobstores import DjangoJobStore
from mytvtime.jobs import update_shows

def start_jobs():
    scheduler = BackgroundScheduler()
    scheduler.add_jobstore(DjangoJobStore(), "default")
    scheduler.add_job(update_shows, 'interval', minutes=1, id='update_all_shows', replace_existing=True)
    scheduler.start()
