from typing import Optional, List, Dict
import discord

from logs import taglog

class AutoModerationConfig:
    def __init__(
            self,
            reporting_channel: Optional[str] = None,
            maximum_reports: int = 3,
            maximum_reports_timestamp_threshold: int = 3600,
            banned_words: Optional[List[str]] = None,
            banned_links: Optional[List[str]] = None,
            ignored_users: Optional[List[str]] = None,
            ignored_roles: Optional[List[str]] = None,
            user_reports: Optional[Dict[str, Dict]] = None):
        self.reporting_channel = reporting_channel
        self.maximum_reports = maximum_reports
        self.maximum_reports_timestamp_threshold = maximum_reports_timestamp_threshold
        self.banned_words = banned_words or []
        self.banned_links = banned_links or []
        self.ignored_users = ignored_users or []
        self.ignored_roles = ignored_roles or []
        self.user_reports = user_reports or {}

    def json(self) -> dict:
        obj = {}
        obj["enabled"] = self.reporting_channel is not None
        obj["reporting_channel"] = self.reporting_channel
        obj["maximum_reports"] = self.maximum_reports
        obj["maximum_reports_timestamp_threshold"] = self.maximum_reports_timestamp_threshold
        obj["banned_words"] = self.banned_words
        obj["banned_links"] = self.banned_links
        obj["ignored_users"] = self.ignored_users
        obj["ignored_roles"] = self.ignored_roles
        obj["user_reports"] = self.user_reports
        return obj
    
    def should_ignore_user(self, user: discord.User) -> bool:
        if str(user.id) in self.ignored_users:
            return True
        
        for role in user.roles:
            if role.name in self.ignored_roles:
                return True
            
        return False
    
    def remove_old_reports(self, user_id: str, reports: List[Dict]) -> List[Dict]:
        current_time = discord.utils.utcnow()
        new_reports = []
        for report in reports:
            report_time = discord.utils.parse_time(report["timestamp"])
            if (current_time - report_time).total_seconds() > self.maximum_reports_timestamp_threshold:
                taglog("AUTOMODCONFIG", f"Removing old report for user {user_id} with timestamp {report['timestamp']}")
            else:
                new_reports.append(report)

        taglog("AUTOMODCONFIG", f"User {user_id} has {len(new_reports)} reports after removing old reports.")
        return new_reports

    def log_suspicious_activity(self, user: discord.User, reason: str | None) -> str | None:
        if self.should_ignore_user(user):
            taglog("AUTOMODCONFIG", f"User {user.name} is ignored, ignoring suspicious activity.")
            return None

        taglog("AUTOMODCONFIG", f"Suspicious activity detected for user {user.name}: {reason}")

        # Add a new report to the user_reports
        new_report = {
            "reason": reason,
            "timestamp": str(discord.utils.utcnow())
        }

        reports_for_user = self.user_reports.get(str(user.id), {"reports": []})["reports"]
        reports_for_user = self.remove_old_reports(str(user.id), reports_for_user)
        reports_for_user.append(new_report)
        self.user_reports[str(user.id)] = {"reports": reports_for_user}
        
        return self.ban_reason(user)

    # Automatically determine if a user should be banned based on the number of reports and the distance between any two reports in time.
    def ban_reason(self, user: discord.User) -> str | None:
        reports_for_user = self.user_reports.get(str(user.id), {"reports": []})["reports"]
        reports_for_user = self.remove_old_reports(str(user.id), reports_for_user)
        self.user_reports[str(user.id)] = {"reports": reports_for_user}

        non_message_tracking_reports = [report for report in reports_for_user if report["reason"] != "message tracking"]
        
        if len(non_message_tracking_reports) >= self.maximum_reports:
            return f"exceeded the maximum number of reports"
        
        for i in range(len(non_message_tracking_reports) - 1):
            timestamp1 = discord.utils.parse_time(reports_for_user[i]["timestamp"])
            timestamp2 = discord.utils.parse_time(reports_for_user[i + 1]["timestamp"])
            time_difference = (timestamp2 - timestamp1).total_seconds()
            
            if time_difference < self.maximum_reports_timestamp_threshold:
                return f"multiple reports within the threshold time"
            
        return None
    
    def check_message(self, message: discord.Message) -> str | None:
        content_lower = message.content.lower()
        
        # Check for banned words and links in the message content
        for word in self.banned_words:
            if word.lower() in content_lower:
                return self.log_suspicious_activity(message.author, f"used a banned word: {word}")
        
        for link in self.banned_links:
            if link.lower() in content_lower:
                return self.log_suspicious_activity(message.author, f"shared a banned link: {link}")

        # Check for spamming behavior
        new_report = {
            "message": message.content,
            "reason": "message tracking",
            "timestamp": str(discord.utils.utcnow())
        }

        reports_for_user = self.user_reports.get(str(message.author.id), {"reports": []})["reports"]
        reports_for_user = self.remove_old_reports(str(message.author.id), reports_for_user)
        reports_for_user.append(new_report)
        self.user_reports[str(message.author.id)] = {"reports": reports_for_user}

        for i in range(len(reports_for_user) - 1):
            messaage1 = reports_for_user[i]["message"]
            message2 = reports_for_user[i + 1]["message"]
            if messaage1 == message2:
                timestamp1 = discord.utils.parse_time(reports_for_user[i]["timestamp"])
                timestamp2 = discord.utils.parse_time(reports_for_user[i + 1]["timestamp"])
                time_difference = (timestamp2 - timestamp1).total_seconds()
                
                if time_difference < self.maximum_reports_timestamp_threshold:
                    return self.log_suspicious_activity(message.author, f"multiple messages within the threshold time")

        return None

    def remove_user_reports(self, user_id: str):
        if user_id in self.user_reports:
            del self.user_reports[user_id]
            taglog("AUTOMODCONFIG", f"Removed all reports for user {user_id}")
        else:
            taglog("AUTOMODCONFIG", f"No reports found for user {user_id} to remove")

