#!/usr/bin/perl
use strict;
use warnings;

use Dpkg::Control::Info;
use Dpkg::Deps;

my $control = Dpkg::Control::Info->new();
my $fields = $control->get_source();
my $build_depends = deps_parse($fields->{'Build-Depends'});
print deps_concat($build_depends) . "\n";
