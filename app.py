from flask import Flask, render_template, request, jsonify, Response
import asyncio
import threading
import json
import time
from queue import Queue
import logging
import traceback

app = Flask(__name__)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Store active processes
active_processes = {}

# Import your existing functions
from ip_changer import process_phone_number

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/start', methods=['POST'])
def start_process():
    try:
        data = request.json
        if not data:
            return jsonify({'error': 'No data received'}), 400
            
        phone_number = data.get('phoneNumber')
        
        if not phone_number or not phone_number.isdigit() or len(phone_number) != 10:
            return jsonify({'error': 'Invalid phone number. Must be 10 digits.'}), 400
        
        # Create unique process ID
        process_id = f"process_{int(time.time())}_{uuid.uuid4().hex[:6]}"
        
        # Create queue for this process
        result_queue = Queue()
        active_processes[process_id] = {
            'queue': result_queue,
            'status': 'running',
            'start_time': time.time()
        }
        
        # Start background thread
        thread = threading.Thread(
            target=run_async_process,
            args=(process_id, phone_number, result_queue)
        )
        thread.daemon = True
        thread.start()
        
        return jsonify({
            'success': True,
            'processId': process_id,
            'message': 'Process started successfully'
        })
        
    except Exception as e:
        logger.error(f"Error starting process: {str(e)}")
        return jsonify({'error': str(e)}), 500

def run_async_process(process_id, phone_number, queue):
    """Run the async process in a separate thread"""
    try:
        # Create new event loop for the thread
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        # Run the main function
        result = loop.run_until_complete(
            process_phone_number(phone_number, queue)
        )
        
        # Send completion
        queue.put({
            'type': 'complete',
            'data': result
        })
        
    except Exception as e:
        logger.error(f"Error in process {process_id}: {str(e)}")
        logger.error(traceback.format_exc())
        queue.put({
            'type': 'error',
            'message': str(e)
        })
    finally:
        if process_id in active_processes:
            active_processes[process_id]['status'] = 'completed'

@app.route('/stream/<process_id>')
def stream(process_id):
    """SSE stream for real-time updates"""
    if process_id not in active_processes:
        return jsonify({'error': 'Process not found'}), 404
    
    def generate():
        queue = active_processes[process_id]['queue']
        
        try:
            while True:
                try:
                    # Get update from queue (timeout to check if process still alive)
                    update = queue.get(timeout=30)
                    
                    # Ensure update is JSON serializable
                    if update:
                        yield f"data: {json.dumps(update)}\n\n"
                    
                    if update.get('type') == 'complete' or update.get('type') == 'error':
                        break
                        
                except Exception as e:
                    # Check if process is still alive
                    if active_processes[process_id]['status'] == 'completed':
                        break
                    continue
        finally:
            # Cleanup
            if process_id in active_processes:
                # Keep for a while then delete
                pass
    
    return Response(
        generate(), 
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'Access-Control-Allow-Origin': '*'
        }
    )

@app.route('/stop/<process_id>', methods=['POST'])
def stop_process(process_id):
    """Stop a running process"""
    if process_id in active_processes:
        active_processes[process_id]['status'] = 'stopping'
        return jsonify({'success': True, 'message': 'Process stopping'})
    return jsonify({'error': 'Process not found'}), 404

@app.route('/status/<process_id>')
def get_status(process_id):
    """Get process status"""
    if process_id in active_processes:
        return jsonify({
            'status': active_processes[process_id]['status'],
            'running': active_processes[process_id]['status'] == 'running'
        })
    return jsonify({'error': 'Process not found'}), 404

# Cleanup old processes (runs every hour)
def cleanup_old_processes():
    """Remove processes older than 1 hour"""
    while True:
        time.sleep(3600)  # 1 hour
        current_time = time.time()
        to_delete = []
        
        for pid, info in active_processes.items():
            if current_time - info.get('start_time', 0) > 3600:
                to_delete.append(pid)
        
        for pid in to_delete:
            del active_processes[pid]
            logger.info(f"Cleaned up old process: {pid}")

# Start cleanup thread
cleanup_thread = threading.Thread(target=cleanup_old_processes, daemon=True)
cleanup_thread.start()

# Add uuid import
import uuid

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True, threaded=True)
