#!/usr/bin/env python3
"""
Import multimodel_conversation_DAG.md into the messaging system.

Parses the conversation file and creates email messages in Maildir format.
Messages are imported as "read" (cur/) to all participant mailboxes.
"""

import re
import sys
import uuid
import time
from pathlib import Path
from datetime import datetime, timedelta
from email.message import EmailMessage
import email.utils

PROJECT_ROOT = Path(__file__).parent.parent
CONVERSATION_FILE = PROJECT_ROOT / "multimodel_conversation_DAG.md"
MESSAGE_DIR = PROJECT_ROOT / ".messages"

# Starting timestamp (work backwards from now)
START_TIME = datetime.now() - timedelta(days=7)  # 7 days ago

def generate_message_id():
    """Generate unique Message-ID."""
    return f"<imported-{uuid.uuid4()}@multimodel.local>"

def parse_conversation(file_path):
    """Parse conversation file into structured messages."""
    with open(file_path, 'r') as f:
        content = f.read()
    
    messages = []
    current_round = []
    current_speaker = None
    current_content = []
    
    lines = content.split('\n')
    
    for line in lines:
        # Check for speaker markers
        if line.startswith('User:'):
            # Save previous message if any
            if current_speaker and current_content:
                current_round.append({
                    'speaker': current_speaker,
                    'content': '\n'.join(current_content).strip()
                })
                current_content = []
            
            # Start new round if we have messages
            if current_round:
                messages.append(current_round)
                current_round = []
            
            # Start user message
            current_speaker = 'coordinator'
            content_start = line[5:].strip()  # Remove "User:"
            if content_start:
                current_content.append(content_start)
        
        elif re.match(r'^(gpt-5|claude-sonnet-4-5-20250929|gemini-2\.5-pro|grok-4)', line):
            # Save previous message if any
            if current_speaker and current_content:
                current_round.append({
                    'speaker': current_speaker,
                    'content': '\n'.join(current_content).strip()
                })
                current_content = []
            
            # Determine speaker
            if line.startswith('gpt-5'):
                current_speaker = 'gpt-5'
            elif line.startswith('claude'):
                current_speaker = 'claude'
            elif line.startswith('gemini'):
                current_speaker = 'gemini'
            elif line.startswith('grok'):
                current_speaker = 'grok'
            
            # Skip the header line (has token counts)
            continue
        
        else:
            # Content line
            if current_speaker:
                current_content.append(line)
    
    # Don't forget the last message and round
    if current_speaker and current_content:
        current_round.append({
            'speaker': current_speaker,
            'content': '\n'.join(current_content).strip()
        })
    if current_round:
        messages.append(current_round)
    
    return messages

def create_email_message(from_role, to_roles, subject, content, reply_to=None, timestamp=None):
    """Create an RFC-compliant email message."""
    msg = EmailMessage()
    
    msg['From'] = f"{from_role}@multimodel.local"
    msg['To'] = ", ".join(f"{role}@multimodel.local" for role in to_roles)
    msg['Subject'] = subject
    msg['Date'] = email.utils.formatdate(timeval=timestamp, localtime=True)
    msg['Message-ID'] = generate_message_id()
    
    if reply_to:
        msg['In-Reply-To'] = reply_to
        msg['References'] = reply_to
    
    msg['X-Role'] = from_role
    msg['X-Imported'] = 'true'
    msg['X-Original-Conversation'] = 'multimodel_conversation_DAG.md'
    
    msg.set_content(content)
    
    return msg

def deliver_as_read(msg, mailbox_name):
    """Deliver message to mailbox as already read (in cur/)."""
    mailbox = MESSAGE_DIR / mailbox_name / "cur"
    
    # Generate filename with Seen flag
    timestamp = int(time.time())
    hostname = "multimodel"
    unique = uuid.uuid4().hex[:8]
    filename = f"{timestamp}.{unique}.{hostname}:2,S"  # :2,S = Seen flag
    
    file_path = mailbox / filename
    with open(file_path, 'w') as f:
        f.write(msg.as_string())
    
    return filename

def import_conversation():
    """Import the conversation into all mailboxes."""
    print(f"Parsing conversation: {CONVERSATION_FILE}")
    rounds = parse_conversation(CONVERSATION_FILE)
    
    print(f"Found {len(rounds)} conversation rounds")
    
    # Participants (all models)
    participants = ['claude', 'gpt-5', 'gemini', 'grok']
    
    # Track message IDs for threading
    current_timestamp = START_TIME.timestamp()
    time_increment = 3600  # 1 hour between rounds
    
    total_messages = 0
    
    for round_idx, round_messages in enumerate(rounds):
        print(f"\n=== Round {round_idx + 1} ===")
        
        # Find coordinator message (should be first in each round)
        coordinator_msg = None
        coordinator_msg_id = None
        model_messages = []
        
        for msg_data in round_messages:
            if msg_data['speaker'] == 'coordinator':
                coordinator_msg = msg_data
            else:
                model_messages.append(msg_data)
        
        if not coordinator_msg:
            print(f"Warning: No coordinator message in round {round_idx + 1}, skipping")
            continue
        
        # Create coordinator message (to all models)
        subject = f"Round {round_idx + 1}: Multi-model discussion"
        if round_idx == 0:
            subject = "Initial conversation: Compositional intelligence ideas"
        
        coordinator_email = create_email_message(
            from_role='coordinator',
            to_roles=participants,
            subject=subject,
            content=coordinator_msg['content'],
            reply_to=None,  # First message in thread
            timestamp=current_timestamp
        )
        
        coordinator_msg_id = coordinator_email['Message-ID']
        
        # Deliver coordinator message to all model mailboxes
        for participant in participants:
            deliver_as_read(coordinator_email, participant)

        # Deliver to monitor (BCC'd on all messages)
        deliver_as_read(coordinator_email, 'monitor')

        print(f"  Coordinator message: {coordinator_email['Subject'][:50]}...")
        print(f"    Delivered to: {', '.join(participants)} + monitor")
        total_messages += 1
        
        current_timestamp += 600  # 10 minutes later
        
        # Create model response messages (all reply to coordinator)
        for msg_data in model_messages:
            speaker = msg_data['speaker']
            
            # Model sends to coordinator (and implicitly other models see it)
            model_email = create_email_message(
                from_role=speaker,
                to_roles=['coordinator'] + [p for p in participants if p != speaker],
                subject=f"Re: {coordinator_email['Subject']}",
                content=msg_data['content'],
                reply_to=coordinator_msg_id,
                timestamp=current_timestamp
            )
            
            # Deliver to all mailboxes (everyone sees all responses)
            for participant in participants:
                deliver_as_read(model_email, participant)

            # Deliver to coordinator (message is TO coordinator)
            deliver_as_read(model_email, 'coordinator')

            # Deliver to monitor (BCC'd on all messages)
            deliver_as_read(model_email, 'monitor')

            print(f"  {speaker} response (length: {len(msg_data['content'])} chars)")
            total_messages += 1
            
            current_timestamp += 300  # 5 minutes between model responses
        
        current_timestamp += time_increment  # Move to next round
    
    print(f"\n=== Import Complete ===")
    print(f"Total messages imported: {total_messages}")
    print(f"Imported to mailboxes: {', '.join(participants)}, coordinator, monitor")
    print(f"All messages marked as read (in cur/)")

    print(f"\nAgents can now reference this conversation:")
    print(f"  msg poll --role claude --all")
    print(f"  mu find 'x-imported:true' maildir:/.messages/claude")
    print(f"\nCoordinator can view in monitor mailbox:")
    print(f"  msg poll --role monitor --all")
    print(f"  mutt -R -f .messages/monitor")

if __name__ == '__main__':
    import_conversation()
