from flask import Flask, render_template, request, jsonify, Response, make_response
import asyncio
import threading
import json
import time
from queue import Queue
import logging
import traceback
import uuid

app = Flask(__name__)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Store active processes
active_processes = {}

# Import your existing functions
try:
    from ip_changer import process_phone_number
    logger.info("✅ Successfully imported ip_changer")
except Exception as e:
    logger.error(f"❌ Failed to import ip_changer: {e}")
    process_phone_number = None

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/health')
def health():
    """Health check endpoint"""
    return jsonify({
        'status': 'ok',
        'time': time.time(),
        'imports': {
            'ip_changer': process_phone_number is not None
        }
    })

@app.route('/start', methods=['POST'])
def start_process():
    try:
        # Log the request
        logger.info(f"Received start request: {request.data}")
        
        # Check content type
        if not request.is_json:
            logger.error("Request is not JSON")
            return jsonify({'error': 'Content-Type must be application/json'}), 400
        
        data = request.get_json()
        logger.info(f"Parsed JSON data: {data}")
        
        if not data:
            return jsonify({'error': 'No data received'}), 400
            
        phone_number = data.get('phoneNumber')
        
        if not phone_number:
            return jsonify({'error': 'Phone number is required'}), 400
            
        if not phone_number.isdigit():
            return jsonify({'error': 'Phone number must contain only digits'}), 400
            
        if len(phone_number) != 10:
            return jsonify({'error': 'Phone number must be exactly 10 digits'}), 400
        
        # Check if ip_changer is imported
        if process_phone_number is None:
            return jsonify({'error': 'ip_changer module not loaded properly'}), 500
        
        # Create unique process ID
        process_id = f"process_{int(time.time())}_{uuid.uuid4().hex[:6]}"
        logger.info(f"Created process ID: {process_id}")
        
        # Create queue for this process
        result_queue = Queue()
        active_processes[process_id] = {
            'queue': result_queue,
            'status': 'running',
            'start_time': time.time(),
            'phone_number': phone_number
        }
        
        # Start background thread
        thread = threading.Thread(
            target=run_async_process,
            args=(process_id, phone_number, result_queue)
        )
        thread.daemon = True
        thread.start()
        
        response_data = {
            'success': True,
            'processId': process_id,
            'message': 'Process started successfully'
        }
        logger.info(f"Sending response: {response_data}")
        return jsonify(response_data)
        
    except Exception as e:
        logger.error(f"Error starting process: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({'error': str(e)}), 500

@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors"""
    return jsonify({'error': 'Endpoint not found'}), 404

@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors"""
    return jsonify({'error': 'Internal server error'}), 500

def run_async_process(process_id, phone_number, queue):
    """Run the async process in a separate thread"""
    logger.info(f"Starting async process for {process_id}")
    
    try:
        # Send initial message
        queue.put({
            'type': 'log',
            'message': f"Starting process for {phone_number}"
        })
        
        # Create new event loop for the thread
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        # Run the main function
        result = loop.run_until_complete(
            process_phone_number(phone_number, queue)
        )
        
        logger.info(f"Process {process_id} completed with result: {result}")
        
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
            'message': f"Process error: {str(e)}"
        })
    finally:
        if process_id in active_processes:
            active_processes[process_id]['status'] = 'completed'
            logger.info(f"Process {process_id} marked as completed")

@app.route('/stream/<process_id>')
def stream(process_id):
    """SSE stream for real-time updates"""
    logger.info(f"Stream request for process: {process_id}")
    
    if process_id not in active_processes:
        logger.warning(f"Process {process_id} not found")
        return jsonify({'error': 'Process not found'}), 404
    
    def generate():
        queue = active_processes[process_id]['queue']
        logger.info(f"Starting stream for process {process_id}")
        
        try:
            # Send initial connection message
            yield f"data: {json.dumps({'type': 'connected', 'message': 'Stream connected'})}\n\n"
            
            while True:
                try:
                    # Get update from queue (timeout to check if process still alive)
                    update = queue.get(timeout=30)
                    
                    # Ensure update is JSON serializable
                    if update:
                        json_str = json.dumps(update)
                        yield f"data: {json_str}\n\n"
                        logger.debug(f"Sent update: {update.get('type')}")
                    
                    if update.get('type') == 'complete' or update.get('type') == 'error':
                        logger.info(f"Stream ending for process {process_id}")
                        break
                        
                except queue.Empty:
                    # Check if process is still alive
                    if active_processes[process_id]['status'] == 'completed':
                        logger.info(f"Process {process_id} completed, ending stream")
                        break
                    continue
                except Exception as e:
                    logger.error(f"Error in stream loop: {e}")
                    continue
        finally:
            logger.info(f"Stream closed for process {process_id}")
            # Cleanup old processes (keep for 5 minutes then delete)
            # You can implement cleanup here
    
    return Response(
        generate(), 
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'Access-Control-Allow-Origin': '*',
            'X-Accel-Buffering': 'no'  # Disable buffering for nginx
        }
    )

@app.route('/stop/<process_id>', methods=['POST'])
def stop_process(process_id):
    """Stop a running process"""
    logger.info(f"Stop request for process: {process_id}")
    
    if process_id in active_processes:
        active_processes[process_id]['status'] = 'stopping'
        # Add stop message to queue
        try:
            active_processes[process_id]['queue'].put({
                'type': 'log',
                'message': 'Process stopped by user'
            })
        except:
            pass
        return jsonify({'success': True, 'message': 'Process stopping'})
    return jsonify({'error': 'Process not found'}), 404

@app.route('/status/<process_id>')
def get_status(process_id):
    """Get process status"""
    if process_id in active_processes:
        return jsonify({
            'status': active_processes[process_id]['status'],
            'running': active_processes[process_id]['status'] == 'running',
            'phone_number': active_processes[process_id].get('phone_number')
        })
    return jsonify({'error': 'Process not found'}), 404

@app.route('/processes')
def list_processes():
    """List all active processes"""
    processes = []
    for pid, info in active_processes.items():
        processes.append({
            'id': pid,
            'status': info['status'],
            'running_time': time.time() - info.get('start_time', time.time()),
            'phone_number': info.get('phone_number')
        })
    return jsonify({'processes': processes})

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

if __name__ == '__main__':
    # Check if ip_changer is loaded
    if process_phone_number is None:
        logger.error("⚠️ WARNING: ip_changer module not loaded!")
    
    logger.info("Starting Flask server...")
    app.run(host='0.0.0.0', port=5000, debug=True, threaded=True)
