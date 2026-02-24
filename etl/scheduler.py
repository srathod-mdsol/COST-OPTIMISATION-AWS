from apscheduler.schedulers.background import BackgroundScheduler
from etl.orchestrator import ETLOrchestrator
from core.logger import setup_logger

logger = setup_logger(__name__)

class ETLScheduler:
    """Schedules and manages periodic ETL synchronization tasks"""
    
    def __init__(self, db_path: str, schedule_time: str = '02:00'):
        self.db_path = db_path
        self.schedule_time = schedule_time
        self.scheduler = BackgroundScheduler()
        self.orchestrator = ETLOrchestrator(db_path)
    
    def start(self):
        """Initialize the background schedule"""
        hour, minute = map(int, self.schedule_time.split(':'))
        logger.info(f"Starting ETL scheduler at daily {self.schedule_time}")
        
        self.scheduler.add_job(
            self.run_daily_job, 
            'cron', 
            hour=hour, 
            minute=minute,
            id='daily_etl_sync'
        )
        self.scheduler.start()
    
    def run_daily_job(self):
        """Execute the daily synchronized ETL run"""
        try:
            logger.info("Starting scheduled daily ETL run")
            self.orchestrator.run_etl(run_type='scheduled', triggered_by='cron')
            logger.info("Scheduled daily ETL run completed successfully")
        except Exception as e:
            logger.error(f"Scheduled ETL run failed: {e}")
    
    def trigger_manual_run(self, user_id: str):
        """Manually trigger the ETL process"""
        return self.orchestrator.run_etl(run_type='manual', triggered_by=user_id)
    
    def shutdown(self):
        """Stop the background scheduler"""
        if self.scheduler.running:
            self.scheduler.shutdown()
