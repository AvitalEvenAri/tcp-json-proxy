# tcp-json-proxy
### Project Description
This project demonstrates a TCP-based client–server system with an intermediate proxy layer.
All communication between components is done using JSON messages over persistent TCP connections.

The system is composed of three main parts: a client, a server, and a proxy.
The client is interactive and allows sending calculation requests or text prompts.
The server processes requests and maintains an internal LRU cache to optimize repeated computations.
The proxy sits between the client and the server and adds an additional caching layer, allowing responses to be served even when the backend server is unavailable.

The project focuses on networking concepts such as persistent connections, application-level protocols over TCP, proxy design, and multi-layer caching.
It also demonstrates how a proxy can reduce load on the server and improve availability by answering cached requests independently.
