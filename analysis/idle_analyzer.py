from typing import Dict, List, Optional
from core.logger import setup_logger
from core.config import Config
from core.constants import (
    CPU_IDLE_THRESHOLD, CPU_CRITICAL_THRESHOLD,
    DB_CONNECTIONS_IDLE_THRESHOLD,
    READ_IOPS_IDLE_THRESHOLD, WRITE_IOPS_IDLE_THRESHOLD,
    NETWORK_IDLE_THRESHOLD,
    DISK_READ_IDLE_THRESHOLD, DISK_WRITE_IDLE_THRESHOLD,
    S3_REQUESTS_IDLE_THRESHOLD,
    ACTIVITY_WEIGHT, CPU_LOW_WEIGHT, CPU_VERY_LOW_WEIGHT,
    NO_CONNECTIONS_WEIGHT, NO_READ_WEIGHT, NO_WRITE_WEIGHT,
    NETWORK_LOW_WEIGHT, DISK_READ_WEIGHT, DISK_WRITE_WEIGHT,
    SEVERITY_CRITICAL_THRESHOLD, SEVERITY_HIGH_THRESHOLD,
    SEVERITY_MEDIUM_THRESHOLD,
    ACTIVITY_GRACE_PERCENTAGE
)

logger = setup_logger(__name__)

class IdleAnalyzer:
    """Analyzes instances for idle status based on metrics and activity"""
    
    @staticmethod
    def analyze_rds(metrics: Dict, last_activity: Dict, activity_threshold_days: int = 30) -> Dict:
        """Analyze RDS metrics and determine idle status."""
        indicators = []
        days_since = last_activity.get('days_since_activity')
        
        # Calculate dynamic thresholds
        grace_period = max(1, activity_threshold_days * ACTIVITY_GRACE_PERCENTAGE)
        
        # If active within grace period, mark as clearly active
        if days_since is not None and days_since < grace_period:
            return {
                'idle_score': 0,
                'severity': 'LOW',
                'indicators': [],
                'idle_reasons': [],
                'active_reasons': [f'Active {days_since:.1f} days ago (within grace period)'],
                'recommendation': f"✅ Instance was recently active {days_since:.1f} days ago"
            }
        
        # CPU-based indicators (using config thresholds)
        cpu_avg = metrics.get('CPUUtilization', {}).get('average', 0)
        if cpu_avg < Config.CPU_IDLE_THRESHOLD:
            indicators.append({
                'name': 'Low CPU Usage',
                'value': f'{cpu_avg:.2f}%',
                'severity': 'high' if cpu_avg < Config.CPU_CRITICAL_THRESHOLD else 'medium',
                'weight': CPU_VERY_LOW_WEIGHT if cpu_avg < Config.CPU_CRITICAL_THRESHOLD else CPU_LOW_WEIGHT
            })
        
        # Connections (using config thresholds)
        conn_avg = metrics.get('DatabaseConnections', {}).get('average', 0)
        if conn_avg < Config.DB_CONNECTIONS_IDLE_THRESHOLD:
            indicators.append({
                'name': 'No Active Connections',
                'value': f'{conn_avg:.2f}',
                'severity': 'high',
                'weight': NO_CONNECTIONS_WEIGHT
            })
        
        # IOPS (using config thresholds)
        read_iops = metrics.get('ReadIOPS', {}).get('average', 0)
        write_iops = metrics.get('WriteIOPS', {}).get('average', 0)
        if read_iops < Config.READ_IOPS_IDLE_THRESHOLD:
            indicators.append({'name': 'No Read Operations', 'value': f'{read_iops:.2f}', 'severity': 'high', 'weight': NO_READ_WEIGHT})
        if write_iops < Config.WRITE_IOPS_IDLE_THRESHOLD:
            indicators.append({'name': 'No Write Operations', 'value': f'{write_iops:.2f}', 'severity': 'high', 'weight': NO_WRITE_WEIGHT})
        
        # Network (using config thresholds)
        net_in = metrics.get('NetworkReceiveThroughput', {}).get('average', 0)
        net_out = metrics.get('NetworkTransmitThroughput', {}).get('average', 0)
        if (net_in + net_out) < Config.NETWORK_IDLE_THRESHOLD:
            indicators.append({'name': 'Minimal Network Activity', 'value': f'{net_in + net_out:.0f} B/s', 'severity': 'medium', 'weight': NETWORK_LOW_WEIGHT})
        
        # Primary Inactivity (using weight constant) - Activity-based idle detection
        if days_since is None or days_since == float('inf'):
            # No activity detected at all in the entire lookback period
            indicators.append({
                'name': f'No Activity in Last {activity_threshold_days} Days',
                'value': 'No activity detected',
                'severity': 'critical',
                'weight': ACTIVITY_WEIGHT
            })
        elif days_since >= activity_threshold_days:
            # Exceeds the user-defined threshold
            indicators.append({
                'name': f'Inactive for {days_since:.1f} Days',
                'value': f'Exceeds {activity_threshold_days}-day threshold',
                'severity': 'critical',
                'weight': ACTIVITY_WEIGHT
            })
        elif days_since >= grace_period:
            # Between grace period and threshold - still worth noting
            # Calculate proportional weight based on how close to threshold
            progress_ratio = (days_since - grace_period) / (activity_threshold_days - grace_period)
            proportional_weight = int(ACTIVITY_WEIGHT * progress_ratio * 0.5)  # Max 50% of full weight
            if proportional_weight >= 10:  # Only add if significant
                indicators.append({
                    'name': f'Inactive for {days_since:.1f} Days',
                    'value': f'Within {activity_threshold_days}-day window',
                    'severity': 'medium',
                    'weight': proportional_weight
                })
        
        idle_score = min(100, sum(ind['weight'] for ind in indicators))
        
        if idle_score >= SEVERITY_CRITICAL_THRESHOLD:
            severity = 'CRITICAL'
            recommendation = f"🚨 CRITICAL: No activity detected in last {activity_threshold_days} days"
        elif idle_score >= SEVERITY_HIGH_THRESHOLD:
            severity = 'HIGH'
            recommendation = f"⚠️ HIGH: Limited activity in {activity_threshold_days}-day window"
        elif idle_score >= SEVERITY_MEDIUM_THRESHOLD:
            severity = 'MEDIUM'
            recommendation = "📊 MEDIUM: Some idle indicators present"
        else:
            severity = 'LOW'
            recommendation = f"✅ LOW: Active within {activity_threshold_days}-day window"
        
        return {
            'idle_score': idle_score,
            'severity': severity,
            'indicators': indicators,
            'idle_reasons': [f"{ind['name']}: {ind['value']}" for ind in indicators],
            'recommendation': recommendation
        }

    @staticmethod
    def analyze_ec2(metrics: Dict, last_activity: Dict, activity_threshold_days: int = 30) -> Dict:
        """
        Analyze EC2 metrics and determine idle status.
        The activity_threshold_days parameter from the UI slider is the DEFINITIVE threshold.
        """
        indicators = []
        days_since = last_activity.get('days_since_activity')
        
        grace_period = max(1, activity_threshold_days * 0.1)
        
        if days_since is not None and days_since < grace_period:
            return {
                'idle_score': 0,
                'severity': 'LOW',
                'indicators': [],
                'idle_reasons': [],
                'active_reasons': [f'Active {days_since:.1f} days ago (within {activity_threshold_days}-day window)'],
                'recommendation': f"✅ Instance was active {days_since:.1f} days ago"
            }
        
        cpu_avg = metrics.get('CPUUtilization', {}).get('average', 0)
        if cpu_avg < 5:
            indicators.append({'name': 'Low CPU Usage', 'value': f'{cpu_avg:.2f}%', 'severity': 'high' if cpu_avg < 1 else 'medium', 'weight': 20})
        
        net_in = metrics.get('NetworkIn', {}).get('average', 0)
        net_out = metrics.get('NetworkOut', {}).get('average', 0)
        if (net_in + net_out) < Config.NETWORK_IDLE_THRESHOLD:
            indicators.append({'name': 'Minimal Network Activity', 'value': f'{net_in + net_out:.0f} B', 'severity': 'high', 'weight': 20})
        
        # Disk (using config thresholds)
        disk_read = metrics.get('DiskReadBytes', {}).get('average', 0)
        disk_write = metrics.get('DiskWriteBytes', {}).get('average', 0)
        if disk_read < Config.DISK_READ_IDLE_THRESHOLD:
            indicators.append({'name': 'No Disk Read Activity', 'value': f'{disk_read:.0f} B', 'severity': 'medium', 'weight': DISK_READ_WEIGHT})
        if disk_write < Config.DISK_WRITE_IDLE_THRESHOLD:
            indicators.append({'name': 'No Disk Write Activity', 'value': f'{disk_write:.0f} B', 'severity': 'medium', 'weight': DISK_WRITE_WEIGHT})
        
        # PRIMARY THRESHOLD CHECK - Activity-based idle detection
        if days_since is None or days_since == float('inf'):
            # No activity detected at all in the entire lookback period
            indicators.append({
                'name': f'No Activity in Last {activity_threshold_days} Days',
                'value': 'No activity detected',
                'severity': 'critical',
                'weight': ACTIVITY_WEIGHT
            })
        elif days_since >= activity_threshold_days:
            # Exceeds the user-defined threshold
            indicators.append({
                'name': f'Inactive for {days_since:.1f} Days',
                'value': f'Exceeds {activity_threshold_days}-day threshold',
                'severity': 'critical',
                'weight': ACTIVITY_WEIGHT
            })
        elif days_since >= grace_period:
            # Between grace period and threshold - still worth noting
            # Calculate proportional weight based on how close to threshold
            progress_ratio = (days_since - grace_period) / (activity_threshold_days - grace_period)
            proportional_weight = int(ACTIVITY_WEIGHT * progress_ratio * 0.5)  # Max 50% of full weight
            if proportional_weight >= 10:  # Only add if significant
                indicators.append({
                    'name': f'Inactive for {days_since:.1f} Days',
                    'value': f'Within {activity_threshold_days}-day window',
                    'severity': 'medium',
                    'weight': proportional_weight
                })
            
        idle_score = min(100, sum(ind['weight'] for ind in indicators))
        
        if idle_score >= SEVERITY_CRITICAL_THRESHOLD:
            severity = 'CRITICAL'
            recommendation = f"🚨 CRITICAL: No activity detected in last {activity_threshold_days} days"
        elif idle_score >= SEVERITY_HIGH_THRESHOLD:
            severity = 'HIGH'
            recommendation = f"⚠️ HIGH: Limited activity in {activity_threshold_days}-day window"
        elif idle_score >= SEVERITY_MEDIUM_THRESHOLD:
            severity = 'MEDIUM'
            recommendation = "📊 MEDIUM: Some idle indicators present"
        else:
            severity = 'LOW'
            recommendation = f"✅ LOW: Active within {activity_threshold_days}-day window"
        
        return {
            'idle_score': idle_score,
            'severity': severity,
            'indicators': indicators,
            'idle_reasons': [f"{ind['name']}: {ind['value']}" for ind in indicators],
            'recommendation': recommendation
        }

    @staticmethod
    def analyze_s3(metrics: Dict, last_activity: Dict, bucket_info: Dict, activity_threshold_days: int = 30) -> Dict:
        """Analyze S3 metrics and determine idle status."""
        indicators = []
        days_since = last_activity.get('days_since_activity')
        
        # S3 often has less frequent access, using S3 specific grace period constant
        from core.constants import S3_GRACE_PERCENTAGE
        grace_period = max(1, activity_threshold_days * S3_GRACE_PERCENTAGE)
        
        if days_since is not None and days_since < grace_period:
            return {
                'idle_score': 0,
                'severity': 'LOW',
                'indicators': [],
                'idle_reasons': [],
                'active_reasons': [f'Active {days_since:.1f} days ago (within grace period)'],
                'recommendation': f"✅ Bucket was active {days_since:.1f} days ago"
            }
        
        all_requests = metrics.get('AllRequests', {}).get('total', metrics.get('AllRequests', {}).get('average', 0))
        if all_requests < Config.S3_REQUESTS_IDLE_THRESHOLD:
            indicators.append({'name': 'Very Low Request Activity', 'value': f'{all_requests:.0f} requests', 'severity': 'high', 'weight': 25})
        
        size_gb = bucket_info.get('size_gb', 0)
        if size_gb < 0.001:  # Size threshold for nearly empty
            indicators.append({'name': 'Empty or Nearly Empty Bucket', 'value': f'{size_gb:.4f} GB', 'severity': 'high', 'weight': 20})
        
        # PRIMARY THRESHOLD CHECK - Activity-based idle detection
        if days_since is None or days_since == float('inf'):
            # No activity detected at all in the entire lookback period
            indicators.append({
                'name': f'No Activity in Last {activity_threshold_days} Days',
                'value': 'No activity detected',
                'severity': 'critical',
                'weight': ACTIVITY_WEIGHT
            })
        elif days_since >= activity_threshold_days:
            # Exceeds the user-defined threshold
            indicators.append({
                'name': f'Inactive for {days_since:.1f} Days',
                'value': f'Exceeds {activity_threshold_days}-day threshold',
                'severity': 'critical',
                'weight': ACTIVITY_WEIGHT
            })
        elif days_since >= grace_period:
            # Between grace period and threshold - still worth noting
            # Calculate proportional weight based on how close to threshold
            progress_ratio = (days_since - grace_period) / (activity_threshold_days - grace_period)
            proportional_weight = int(ACTIVITY_WEIGHT * progress_ratio * 0.5)  # Max 50% of full weight
            if proportional_weight >= 10:  # Only add if significant
                indicators.append({
                    'name': f'Inactive for {days_since:.1f} Days',
                    'value': f'Within {activity_threshold_days}-day window',
                    'severity': 'medium',
                    'weight': proportional_weight
                })
            
        idle_score = min(100, sum(ind['weight'] for ind in indicators))
        
        if idle_score >= SEVERITY_CRITICAL_THRESHOLD:
            severity = 'CRITICAL'
            recommendation = f"🚨 CRITICAL: No activity detected in last {activity_threshold_days} days"
        elif idle_score >= SEVERITY_HIGH_THRESHOLD:
            severity = 'HIGH'
            recommendation = f"⚠️ HIGH: Limited activity in {activity_threshold_days}-day window"
        elif idle_score >= SEVERITY_MEDIUM_THRESHOLD:
            severity = 'MEDIUM'
            recommendation = "📊 MEDIUM: Some idle indicators present"
        else:
            severity = 'LOW'
            recommendation = f"✅ LOW: Active within {activity_threshold_days}-day window"
        
        return {
            'idle_score': idle_score,
            'severity': severity,
            'indicators': indicators,
            'idle_reasons': [f"{ind['name']}: {ind['value']}" for ind in indicators],
            'recommendation': recommendation
        }

    @staticmethod
    def analyze_ebs(metrics: Dict, last_activity: Dict, activity_threshold_days: int = 30) -> Dict:
        """Analyze EBS metrics and determine idle status."""
        indicators = []
        days_since = last_activity.get('days_since_activity')
        
        grace_period = max(1, activity_threshold_days * ACTIVITY_GRACE_PERCENTAGE)
        
        if days_since is not None and days_since < grace_period:
            return {
                'idle_score': 0,
                'severity': 'LOW',
                'indicators': [],
                'idle_reasons': [],
                'active_reasons': [f'Active {days_since:.1f} days ago (within grace period)'],
                'recommendation': f"✅ Volume was active {days_since:.1f} days ago"
            }
        
        read_ops = metrics.get('VolumeReadOps', {}).get('average', 0)
        write_ops = metrics.get('VolumeWriteOps', {}).get('average', 0)
        if read_ops < Config.READ_IOPS_IDLE_THRESHOLD:
            indicators.append({'name': 'No Read Ops', 'value': f'{read_ops:.2f}', 'severity': 'high', 'weight': NO_READ_WEIGHT})
        if write_ops < Config.WRITE_IOPS_IDLE_THRESHOLD:
            indicators.append({'name': 'No Write Ops', 'value': f'{write_ops:.2f}', 'severity': 'high', 'weight': NO_WRITE_WEIGHT})
            
        read_bytes = metrics.get('VolumeReadBytes', {}).get('average', 0)
        write_bytes = metrics.get('VolumeWriteBytes', {}).get('average', 0)
        if read_bytes < Config.DISK_READ_IDLE_THRESHOLD:
            indicators.append({'name': 'Minimal Read Bytes', 'value': f'{read_bytes:.0f} B', 'severity': 'medium', 'weight': DISK_READ_WEIGHT})
        if write_bytes < Config.DISK_WRITE_IDLE_THRESHOLD:
            indicators.append({'name': 'Minimal Write Bytes', 'value': f'{write_bytes:.0f} B', 'severity': 'medium', 'weight': DISK_WRITE_WEIGHT})
        
        # PRIMARY THRESHOLD CHECK - Activity-based idle detection
        if days_since is None or days_since == float('inf'):
            # No activity detected at all in the entire lookback period
            indicators.append({
                'name': f'No Activity in Last {activity_threshold_days} Days',
                'value': 'No activity detected',
                'severity': 'critical',
                'weight': ACTIVITY_WEIGHT
            })
        elif days_since >= activity_threshold_days:
            # Exceeds the user-defined threshold
            indicators.append({
                'name': f'Inactive for {days_since:.1f} Days',
                'value': f'Exceeds {activity_threshold_days}-day threshold',
                'severity': 'critical',
                'weight': ACTIVITY_WEIGHT
            })
        elif days_since >= grace_period:
            # Between grace period and threshold - still worth noting
            # Calculate proportional weight based on how close to threshold
            progress_ratio = (days_since - grace_period) / (activity_threshold_days - grace_period)
            proportional_weight = int(ACTIVITY_WEIGHT * progress_ratio * 0.5)  # Max 50% of full weight
            if proportional_weight >= 10:  # Only add if significant
                indicators.append({
                    'name': f'Inactive for {days_since:.1f} Days',
                    'value': f'Within {activity_threshold_days}-day window',
                    'severity': 'medium',
                    'weight': proportional_weight
                })
            
        idle_score = min(100, sum(ind['weight'] for ind in indicators))
        
        if idle_score >= SEVERITY_CRITICAL_THRESHOLD:
            severity = 'CRITICAL'
            recommendation = f"🚨 CRITICAL: No activity detected in last {activity_threshold_days} days"
        elif idle_score >= SEVERITY_HIGH_THRESHOLD:
            severity = 'HIGH'
            recommendation = f"⚠️ HIGH: Limited activity in {activity_threshold_days}-day window"
        elif idle_score >= SEVERITY_MEDIUM_THRESHOLD:
            severity = 'MEDIUM'
            recommendation = "📊 MEDIUM: Some idle indicators present"
        else:
            severity = 'LOW'
            recommendation = f"✅ LOW: Active within {activity_threshold_days}-day window"
        
        return {
            'idle_score': idle_score,
            'severity': severity,
            'indicators': indicators,
            'idle_reasons': [f"{ind['name']}: {ind['value']}" for ind in indicators],
            'recommendation': recommendation
        }
