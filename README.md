webdav-python
=============

Authenticate
==========
* Simple authority
```
$ webdav login https://webdav.yandex.ru
webdav_login: login
webdav_password: pass
```

* Authenticate with root directory
```
$ webdav login https://webdav.yandex.ru -r dir1
webdav_login: login
webdav_password: pass
```

* Authenticate with proxy
```
$ webdav login https://webdav.yandex.ru -p http://127.0.0.1:8080
webdav_login: w_login
webdav_password: w_pass
proxy_login: p_login
proxy_password: p_password
```

Actions
==========
* Check
```
$ webdav check dir1/file1
success
```
* Free
```
$ webdav free
204331432956
```

* List
```
$ webdav ls dir1
dir2/
dir3/
file1
file2
```
* Clean
```
$ webdav clean dir1/
$ webdav clean file1
```

* Mkdir
```
$ webdav mkdir dir1
```

* Copy
```
$ webdav copy dir1/file1 -t dir2/file1
```

* Move
```
$ webdav move dir1/file1 -t dir1/file2
```

* Download
```
$ webdav download dir1/file1 -t ~/Downloads/file1
```

* Upload
```
$ webdav upload dir1/file1 -f ~/Downloads/file1
```

* Publish
```
$ webdav publish dir1/file1
https://yadi.sk/d/Ip5xckjBc9NQD
```

* Unpublish
```
$ webdav unpublish dir1/file1
```
