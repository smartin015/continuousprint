# A simple command parser client that connects to headless server instances.

import zmq
import sys
import argparse
import logging
import os
import yaml

def main():
    parser = argparse.ArgumentParser(description='Debug client for main_headless')
    parser.add_argument('base_dir', help='Base directory matching that of main_headless instance')
    args = parser.parse_args()

    with open(os.path.join(args.base_dir, "server.yaml"), 'r') as f:
      data = yaml.safe_load(f.read())

    logging.basicConfig(level=logging.DEBUG)
    context = zmq.Context()
    socket = context.socket(zmq.REQ)
    logging.info(f"Connecting to {data['debug_socket']}")
    socket.connect(data['debug_socket'])
    while True:
      socket.send_string(input(">> "))
      sys.stdout.write(socket.recv().decode('utf8'))
    
if __name__ == "__main__":
  main()
