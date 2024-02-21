Initial Ideas
=============

I initially built something using Flask and a relational DB as these are the tools 
I'm familiar with. It worked ok and the structure is still similar to the code here,
but using fastAPI feels more like the right tool for the job!

Data
----

The data behind this API is probably about as fixed as it gets since it 
represents countries! In the upstream API even attributes which could be
changeable (like population) don't appear to be current. The data being invalid
would normally be an issue but isn't as applicable here.

With that in mind, it's not unreasonable to populate a local DB with all the 
information ahead of starting the app. Similarly, if storing data for each 
country as it's requested there isn't much reason not to get all the data for 
a specific country, even if only a few attributes are needed. Then any subsequent 
API calls can use the local data.

Initial Build
-------------

The initial build was a basic synchronous+tasks API, with three endpoints.
All requests are synchronous, but POST-ing to compare two countries
creates a resource representing a comparison task, where the 
state and result is supplied by the given URL after the POST request.
However, because flask apps are WSGI and don't support long running asyncio 
tasks (even after converting with `asgiref.wsgi.WsgiToAsgi`) the background 
tasks are processed via Celery and a task queue.


Advantages: 
- Basic flask app, so can use flask extensions and other libraries which work with it
- Doesn't need asyncio directly
- Scalable as external processing performed separately

Disadvantages:
- Not actually asynchronous
- Requires separate processes for celery, task queue and app itself
- Expensive since tasks require a separate process

In terms of data management the relational DB also requires a clearly defined data model,
but the content from the upstream API is quite varied and making such a model would probably
involve some thought about what our API users actually want!

FastAPI Build
-------------

Presumably people actually like the API we're building on and find it useful! They
may also expect something built on that API not to drop results they would get otherwise.
So instead of a relational DB, we can use a noSQL DB (mongoDB) which can store more arbitrary
data - all we're saying is the data will be in the restcountries format.

We're also using fastAPI because I hadn't used it before and it has better
support for async operations, including tasks which last beyond the lifetime of a 
single request. It also has in built support for swagger-ui to test things, which was one
of the reasons I had wanted to use flask & connexion in the first place..

Running Things
--------------
The app and dependencies can be installed in a virtual python environment like `conda`. A running mongodb instance 
also needs to be available on port 27017. This could either be a local install or with 
`docker run -p 27017:27017 --name country-db -d mongo`.

The project can also be built with docker compose using the `docker-compose.yml` file.
