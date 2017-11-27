# fabricator
A fabric script to deploy Phacility's Phabricator on any Debian / Debian-based linux flavor.


## Installation

1. `git clone git@github.com:dhilipsiva/fabricator.git`
1. `cd fabricator`
1. `cp .env.template .env` And change your settings in this new .env file
1. `pipenv  --two` Create a new python 2 env using [pipenv]()
1. `pipenv shell` Open and activate the environment
1. `pipenv install` Install all the requirements
1. `fab setup` This will setup a new instance
1. `fab upgrade` If you need to upgrade your phabiricator to the latest, use this.
