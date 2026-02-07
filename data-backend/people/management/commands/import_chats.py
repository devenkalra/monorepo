"""
Django management command to import chat conversations as Note entities
"""

from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.models import User
from people.models import Note
import json
from datetime import datetime
from markdown import markdown


class Command(BaseCommand):
    help = 'Import chat conversations as Note entities (ChatGPT, Gemini formats)'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--source',
            type=str,
            required=True,
            choices=['chatgpt', 'gemini', 'claude', 'other'],
            help='Source of the chat export'
        )
        parser.add_argument(
            '--file',
            type=str,
            required=True,
            help='Path to the JSON file to import'
        )
        parser.add_argument(
            '--user',
            type=str,
            required=True,
            help='Username or email of the user to assign notes to'
        )
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Print detailed progress'
        )
    
    def handle(self, *args, **options):
        source = options['source']
        file_path = options['file']
        username = options['user']
        verbose = options.get('verbose', False)
        
        # Get user
        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            try:
                user = User.objects.get(email=username)
            except User.DoesNotExist:
                raise CommandError(f"User '{username}' not found")
        
        if verbose:
            self.stdout.write(f"Importing conversations for user: {user.username}")
        
        # Load JSON file
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except FileNotFoundError:
            raise CommandError(f"File not found: {file_path}")
        except json.JSONDecodeError as e:
            raise CommandError(f"Invalid JSON: {e}")
        
        # Parse based on source
        if source == 'chatgpt':
            conversations = self.parse_chatgpt(data)
        elif source == 'gemini':
            conversations = self.parse_gemini(data)
        elif source == 'claude':
            conversations = self.parse_claude(data)
        else:
            conversations = self.parse_generic(data)
        
        # Import conversations as Notes
        imported_count = 0
        for conv_data in conversations:
            try:
                # Generate HTML description
                html_description = self.generate_html_description(conv_data, source)
                
                # Determine source tag
                source_tag = source.capitalize()  # ChatGPT, Gemini, Claude, Other
                
                # Create or update Note
                note, created = Note.objects.update_or_create(
                    user=user,
                    display=conv_data['title'],  # Note uses 'display' not 'label'
                    defaults={
                        'description': html_description,
                        'tags': ['Conversation', source_tag],
                    }
                )
                
                imported_count += 1
                
                if verbose:
                    action = "Created" if created else "Updated"
                    self.stdout.write(f"  {action}: {conv_data['title']}")
                    
            except Exception as e:
                self.stderr.write(f"Error importing conversation '{conv_data.get('title', 'Unknown')}': {e}")
                continue
        
        self.stdout.write(
            self.style.SUCCESS(
                f"\n✓ Successfully imported {imported_count} conversations from {source}"
            )
        )
    
    def generate_html_description(self, conv_data, source):
        """Generate HTML description from conversation turns"""
        turns = conv_data.get('turns', [])
        title = conv_data.get('title', 'Untitled Conversation')
        started_at = conv_data.get('started_at')
        
        html_parts = []
        
        # Header
        html_parts.append('<div class="conversation-header">')
        html_parts.append(f'<h2>{self._escape_html(title)}</h2>')
        html_parts.append(f'<p><strong>Source:</strong> {source.capitalize()}</p>')
        if started_at:
            html_parts.append(f'<p><strong>Date:</strong> {started_at}</p>')
        html_parts.append(f'<p><strong>Turns:</strong> {len(turns)}</p>')
        html_parts.append('</div>')
        html_parts.append('<hr>')
        
        # Table of Contents
        html_parts.append('<div id="toc" class="table-of-contents">')
        html_parts.append('<h3>Table of Contents</h3>')
        html_parts.append('<ol>')
        
        user_turn_count = 0
        for i, turn in enumerate(turns):
            if turn.get('role') == 'user':
                user_turn_count += 1
                summary = self._get_turn_summary(turn.get('content', ''))
                html_parts.append(f'<li><a href="#turn-{i}">{summary}</a></li>')
        
        html_parts.append('</ol>')
        html_parts.append('</div>')
        html_parts.append('<hr>')
        
        # Conversation turns
        html_parts.append('<div class="conversation-turns">')
        
        for i, turn in enumerate(turns):
            role = turn.get('role', 'unknown')
            content = turn.get('content', '')
            timestamp = turn.get('timestamp', '')
            
            # Anchor for TOC navigation
            html_parts.append(f'<a id="turn-{i}" style="display: block; position: relative; top: -100px; visibility: hidden;"></a>')
            
            # Turn container
            html_parts.append(f'<div class="turn turn-{role}">')
            
            # Turn header with "Top" link
            html_parts.append('<div class="turn-header">')
            html_parts.append(f'<strong>{role.capitalize()}</strong>')
            if timestamp:
                html_parts.append(f' <span class="timestamp">({timestamp})</span>')
            html_parts.append(' <a href="#toc" class="top-link">↑ Top</a>')
            html_parts.append('</div>')
            
            # Turn content (convert markdown to HTML)
            html_parts.append('<div class="turn-content">')
            try:
                html_content = markdown(content)
                html_parts.append(html_content)
            except:
                html_parts.append(f'<p>{self._escape_html(content)}</p>')
            html_parts.append('</div>')
            
            html_parts.append('</div>')
        
        html_parts.append('</div>')
        
        return '\n'.join(html_parts)
    
    def _get_turn_summary(self, content, max_length=80):
        """Get a short summary of a turn for TOC"""
        # Remove markdown formatting
        content = content.replace('#', '').replace('*', '').replace('`', '')
        # Take first line or sentence
        lines = content.split('\n')
        first_line = lines[0].strip() if lines else content
        # Truncate if too long
        if len(first_line) > max_length:
            return first_line[:max_length] + '...'
        return first_line
    
    def _escape_html(self, text):
        """Escape HTML special characters"""
        return (text
                .replace('&', '&amp;')
                .replace('<', '&lt;')
                .replace('>', '&gt;')
                .replace('"', '&quot;')
                .replace("'", '&#39;'))
    
    def parse_chatgpt(self, data):
        """Parse ChatGPT export format"""
        conversations = []
        
        # ChatGPT format is a list of conversations (or might be wrapped)
        conv_list = data if isinstance(data, list) else [data]
        
        for conv in conv_list:
            conversation_id = conv.get('id', conv.get('conversation_id'))
            title = conv.get('title', 'Untitled Conversation')
            
            # Get mapping (message_id -> message)
            mapping = conv.get('mapping', {})
            
            # Build turns from mapping
            turns = []
            for msg_id, msg_data in mapping.items():
                message = msg_data.get('message')
                if not message:
                    continue
                
                author_role = message.get('author', {}).get('role')
                if author_role not in ['user', 'assistant']:
                    continue
                
                content_parts = message.get('content', {}).get('parts', [])
                content = '\n'.join(str(part) for part in content_parts if part)
                
                if not content:
                    continue
                
                timestamp = message.get('create_time')
                if timestamp:
                    try:
                        timestamp = datetime.fromtimestamp(timestamp).isoformat()
                    except:
                        timestamp = None
                
                turns.append({
                    'role': author_role,
                    'content': content,
                    'timestamp': timestamp
                })
            
            if turns:
                conversations.append({
                    'conversation_id': conversation_id,
                    'title': title,
                    'turns': turns,
                    'started_at': turns[0].get('timestamp') if turns else None
                })
        
        return conversations
    
    def parse_gemini(self, data):
        """Parse Google Gemini export format"""
        conversations = []
        
        # Gemini wraps conversations in a "conversations" array
        conv_list = data.get('conversations', data if isinstance(data, list) else [data])
        
        for conv in conv_list:
            conversation_id = conv.get('id', conv.get('conversation_id'))
            title = conv.get('title', 'Untitled Conversation')
            
            turns = []
            for turn in conv.get('turns', []):
                role = turn.get('role', 'user')
                content = turn.get('content', turn.get('text', ''))
                timestamp = turn.get('timestamp')
                
                if content:
                    turns.append({
                        'role': role,
                        'content': content,
                        'timestamp': timestamp
                    })
            
            if turns:
                conversations.append({
                    'conversation_id': conversation_id,
                    'title': title,
                    'turns': turns,
                    'started_at': turns[0].get('timestamp') if turns else None
                })
        
        return conversations
    
    def parse_claude(self, data):
        """Parse Claude export format"""
        # Similar to Gemini format
        return self.parse_gemini(data)
    
    def parse_generic(self, data):
        """Parse generic conversation format"""
        return self.parse_gemini(data)
