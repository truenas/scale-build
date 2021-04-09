#!/usr/bin/perl
use strict;
use warnings;

use Dpkg::Control::Info;
use Dpkg::Deps;
use JSON;

my ($path) = @ARGV;
my $control = Dpkg::Control::Info->new($path);
my $fields = $control->get_source();
my $build_depends = deps_parse($fields->{'Build-Depends'});
my %src_package_info = ('name'=> $fields->{'Source'}, 'build_depends'=> deps_concat($build_depends));

my @packages = $control->get_packages();
my @packages_list;
foreach my $package (@packages)
{
    push(@packages_list, {
        'name' => $package->{'Package'},
        'depends' => $package->{'Depends'}
    });
}
my %package_info = ('source_package'=> \%src_package_info, 'binary_packages'=> \@packages_list);
my $json_str = encode_json \%package_info;
print("$json_str");
