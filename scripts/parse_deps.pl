#!/usr/bin/perl
use strict;
use warnings;

use Dpkg::Control::Info;
use Dpkg::Deps;
use JSON;

my ($path, $depends_type) = @ARGV;
my $control = Dpkg::Control::Info->new($path);
if ($depends_type eq 'Build-Depends'){
    my $fields = $control->get_source();
    my $build_depends = deps_parse($fields->{'Build-Depends'});
    my %package_info = ('name'=> $fields->{'Source'}, 'build_depends'=> deps_concat($build_depends));
    my $json_str = encode_json \%package_info;
    print("$json_str");
} elsif ($depends_type eq 'Depends') {
    my @packages = $control->get_packages();
    my @packages_list;
    foreach my $package (@packages)
    {
        push(@packages_list, {
            'name' => $package->{'Package'},
            'depends' => $package->{'Depends'}
        });
    }
    my $json_str = encode_json(\@packages_list);
    print("$json_str");
} else {
    die "Unrecognized depends_type specified";
}
